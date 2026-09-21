from __future__ import annotations

from dataclasses import dataclass


ALLOWED_TOOLS_BY_TASK = {
    "catalogue_generation": {"read_product_blob"},
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    severity: str


def authorize_tool(task: str, tool_name: str, security_mode: str) -> PolicyDecision:
    if security_mode == "vulnerable":
        if tool_name not in {"read_product_blob", "download_and_execute_script"}:
            return PolicyDecision(False, "Unknown capability is never authorized.", "blocked")
        return PolicyDecision(True, "Tool is authorized for the current workflow.", "success")
    allowed_tools = ALLOWED_TOOLS_BY_TASK.get(task, set())
    if tool_name not in allowed_tools:
        return PolicyDecision(
            False,
            f"Tool {tool_name} is outside the capability set authorized for {task}.",
            "blocked",
        )
    return PolicyDecision(True, "Tool is authorized for the current task.", "success")
