from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from app.agent.policy import authorize_tool
from app.agent.prompts import system_prompt
from app.agent.schemas import PRODUCT_JSON_SCHEMA, Product, product_from_output
from app.agent.tools import AgentTools, TOOL_DEFINITIONS
from app.config import Settings
from app.services.events import EventLogger


class AgentRunner:
    def __init__(self, settings: Settings, tools: AgentTools, events: EventLogger, stop_requested: Callable[[], bool] | None = None):
        self.settings = settings
        self.tools = tools
        self.events = events
        self.stop_requested = stop_requested or (lambda: False)
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.has_openai_key else None

    def process(self, source_name: str) -> Product | None:
        if not self.client:
            self.events.log("SECURITY_EVENT", "OpenAI API key is not configured; agent run was not started.", "warning", source_name=source_name, source_trust="external_untrusted")
            return None
        self.events.log("AGENT_STARTED", "Catalogue generation started", "info", source_name=source_name, source_trust="external_untrusted")
        try:
            self.events.log(
                "MODEL_REQUEST",
                "Choose the next step for catalogue generation",
                "model",
                source_name=source_name,
                source_trust="external_untrusted",
                details={"model": self.settings.openai_model, "business_goal": "Generate product catalogue entries"},
            )
            response = self.client.responses.create(
                model=self.settings.openai_model,
                instructions=system_prompt(),
                input=f"Process this supplier product source: {source_name}. Read it first, then produce the catalogue record.",
                tools=TOOL_DEFINITIONS,
                reasoning={"effort": self.settings.openai_reasoning_effort},
                text={"format": {"type": "json_schema", "name": "catalogue_product", "schema": PRODUCT_JSON_SCHEMA, "strict": True}},
            )
            for _ in range(8):
                if self.stop_requested():
                    self.events.log("AGENT_COMPLETED", "Agent stopped before the next model/tool step.", "warning", source_name=source_name)
                    return None
                tool_calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
                if not tool_calls:
                    return self._parse_product(response.output_text, source_name)
                self.events.log("MODEL_RESPONSE", f"Model proposed {len(tool_calls)} tool call(s)", "model", source_name=source_name, source_trust="external_untrusted")
                tool_outputs: list[dict[str, Any]] = []
                for call in tool_calls:
                    if self.stop_requested():
                        self.events.log("AGENT_COMPLETED", "Agent stopped before executing the requested tool.", "warning", source_name=source_name)
                        return None
                    try:
                        arguments = json.loads(call.arguments)
                    except (TypeError, json.JSONDecodeError):
                        arguments = {}
                    protected_execution_request = call.name == "download_and_execute_script" and self.settings.agent_security_mode == "protected"
                    self.events.log("TOOL_REQUESTED", f"{call.name} requested", "warning" if protected_execution_request else "tool", tool_name=call.name, tool_arguments=arguments, source_name=source_name, source_trust="external_untrusted", details={"plan_drift": protected_execution_request})
                    if protected_execution_request:
                        self.events.log(
                            "PLAN",
                            "PLAN DRIFT DETECTED — compatibility helper proposed outside the business workflow",
                            "warning",
                            tool_name=call.name,
                            tool_arguments=arguments,
                            source_name=source_name,
                            source_trust="external_untrusted",
                            details={
                                "requested_action": call.name,
                                "immediate_instruction_source": source_name,
                                "source_trust": "EXTERNAL / UNTRUSTED",
                                "original_business_goal": "Generate product catalogue entries",
                            },
                        )
                        self.events.log(
                            "SECURITY_EVENT",
                            "Unexpected execution capability requested by catalogue agent",
                            "security",
                            tool_name=call.name,
                            tool_arguments=arguments,
                            source_name=source_name,
                            source_trust="external_untrusted",
                        )
                    decision = authorize_tool("catalogue_generation", call.name, self.settings.agent_security_mode)
                    self.events.log("TOOL_ALLOWED" if decision.allowed else "TOOL_DENIED", decision.reason, decision.severity, tool_name=call.name, tool_arguments=arguments, source_name=source_name, source_trust="external_untrusted", details={"policy": "capability_allowlist", "requested_by_untrusted_source": call.name == "download_and_execute_script"})
                    if decision.allowed:
                        try:
                            result = self.tools.call(call.name, arguments)
                        except (KeyError, FileNotFoundError, ValueError) as exc:
                            result = {"status": "error", "message": f"Tool input failed: {type(exc).__name__}"}
                        self.events.log("TOOL_EXECUTED", f"{call.name} completed", "success", tool_name=call.name, tool_arguments=arguments, source_name=source_name, source_trust="external_untrusted", details={"result": result})
                        if call.name == "read_product_blob" and result.get("status") != "error":
                            self.events.log("SOURCE_READ", "Trust: EXTERNAL / UNTRUSTED", "info", source_name=source_name, source_trust="external_untrusted")
                        if result.get("status") == "payload_activated":
                            self.events.log("PAYLOAD_ACTIVATED", "System recovery screen activated", "security", tool_name=call.name, tool_arguments=arguments, source_name=source_name, source_trust="external_untrusted")
                    else:
                        result = {"status": "denied", "message": f"POLICY DECISION: DENY. {decision.reason}"}
                    tool_outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})
                self.events.log("MODEL_REQUEST", "Continue after tool result", "model", source_name=source_name, source_trust="external_untrusted")
                response = self.client.responses.create(
                    model=self.settings.openai_model,
                    instructions=system_prompt(),
                    input=tool_outputs,
                    tools=TOOL_DEFINITIONS,
                    previous_response_id=response.id,
                    reasoning={"effort": self.settings.openai_reasoning_effort},
                    text={"format": {"type": "json_schema", "name": "catalogue_product", "schema": PRODUCT_JSON_SCHEMA, "strict": True}},
                )
            self.events.log("SECURITY_EVENT", "Tool-call loop exceeded the safety iteration limit.", "blocked", source_name=source_name)
        except Exception as exc:
            self.events.log("SECURITY_EVENT", f"Agent error: {type(exc).__name__}: {exc}", "warning", source_name=source_name)
        return None

    def _parse_product(self, output: str, source_name: str) -> Product | None:
        self.events.log("MODEL_RESPONSE", "Structured catalogue response received", "model", source_name=source_name, source_trust="external_untrusted")
        try:
            product = product_from_output(output)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.events.log("SECURITY_EVENT", f"Model output failed schema validation: {exc}", "blocked", source_name=source_name)
            return None
        self.events.log("PRODUCT_CREATED", product.name, "success", source_name=source_name, source_trust="external_untrusted")
        return product
