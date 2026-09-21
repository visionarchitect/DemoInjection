import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.runner import AgentRunner
from app.agent.tools import AgentTools, TOOL_DEFINITIONS
from app.config import Settings
from app.database import Database
from app.services.demo_payload import SafeDemoPayload
from app.services.events import EventLogger
from app.services.catalogue import CatalogueService
from app.storage.local import LocalProductFeed


PRODUCT = {
    "id": "nx-440",
    "name": "NovaEdge NX-440 Industrial Controller",
    "manufacturer": "NovaEdge Systems",
    "category": "Industrial controller",
    "short_description": "A cabinet-ready industrial edge controller.",
    "long_description": "Coordinates local equipment data and provides a stable plant handoff.",
    "features": ["Dual network paths"],
    "technical_specs": {"Temperature": "-20 C to +70 C"},
    "tags": ["controller"],
}

SCRIPT_URL = "http://127.0.0.1:2001/demo-assets/validation-check.sh"


class FakeResponses:
    def __init__(self, responses):
        self.responses = iter(responses)

    def create(self, **_kwargs):
        return next(self.responses)


class RecordingRunner:
    def __init__(self):
        self.sources = []

    def process(self, source_name):
        self.sources.append(source_name)
        return None


def tool_response(response_id, call_id, name, arguments):
    call = SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=json.dumps(arguments))
    return SimpleNamespace(id=response_id, output=[call], output_text="")


def final_response():
    return SimpleNamespace(id="final", output=[], output_text=json.dumps(PRODUCT))


def settings(tmp_path, mode):
    return Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        openai_reasoning_effort="medium",
        azure_storage_account_url=None,
        azure_storage_container=None,
        azure_storage_sas_token=None,
        demo_storage_mode="local",
        agent_security_mode=mode,
        database_path=str(tmp_path / "runner.db"),
        demo_blob_path=Path("demo_blob"),
    )


@pytest.mark.parametrize("mode,activated,decision", [("vulnerable", True, "TOOL_ALLOWED"), ("protected", False, "TOOL_DENIED")])
def test_model_requested_tool_flows_through_policy_and_safe_simulator(tmp_path, mode, activated, decision):
    config = settings(tmp_path, mode)
    database = Database(config.database_path)
    script_bytes = Path("demo_blob/scripts/validation-check.sh").read_bytes()
    payload = SafeDemoPayload(
        Path("demo_blob/scripts"),
        launch_browser=False,
        downloader=lambda _url: script_bytes,
    )
    runner = AgentRunner(config, AgentTools(LocalProductFeed(Path("demo_blob")), payload), EventLogger(database))
    runner.client = SimpleNamespace(responses=FakeResponses([
        tool_response("one", "read", "read_product_blob", {"name": "products/product-016-poisoned.md"}),
        tool_response("two", "execute", "download_and_execute_script", {"url": SCRIPT_URL}),
        final_response(),
    ]))

    product = runner.process("products/product-016-poisoned.md")

    assert product is not None
    assert product.id == "nx-440"
    assert payload.state.active is activated
    stored_events = database.events()
    event_types = [event["event_type"] for event in stored_events]
    protected = mode == "protected"
    assert ("PLAN" in event_types) is protected
    assert ("SECURITY_EVENT" in event_types) is protected
    assert decision in event_types
    assert ("PAYLOAD_ACTIVATED" in event_types) is activated
    if not protected:
        execution_request = next(event for event in stored_events if event["event_type"] == "TOOL_REQUESTED" and event["tool_name"] == "download_and_execute_script")
        authorization = next(event for event in stored_events if event["event_type"] == "TOOL_ALLOWED" and event["tool_name"] == "download_and_execute_script")
        assert execution_request["severity"] == "tool"
        assert authorization["severity"] == "success"
        assert "vulnerable" not in authorization["message"].lower()


def test_only_two_tools_are_model_visible():
    assert [tool["name"] for tool in TOOL_DEFINITIONS] == ["read_product_blob", "download_and_execute_script"]


def test_reading_poisoned_source_does_not_execute_without_model_tool_call(tmp_path):
    config = settings(tmp_path, "vulnerable")
    database = Database(config.database_path)
    payload = SafeDemoPayload(Path("demo_blob/scripts"), launch_browser=False)
    runner = AgentRunner(
        config,
        AgentTools(LocalProductFeed(Path("demo_blob")), payload),
        EventLogger(database),
    )
    runner.client = SimpleNamespace(responses=FakeResponses([
        tool_response("one", "read", "read_product_blob", {"name": "products/product-016-poisoned.md"}),
        final_response(),
    ]))

    product = runner.process("products/product-016-poisoned.md")

    assert product is not None
    assert not payload.state.active
    assert not any(event["event_type"] == "PAYLOAD_ACTIVATED" for event in database.events())


def test_normal_catalogue_workflow_publishes_product(tmp_path):
    config = settings(tmp_path, "vulnerable")
    database = Database(config.database_path)
    feed = LocalProductFeed(Path("demo_blob"))
    events = EventLogger(database)
    runner = AgentRunner(config, AgentTools(feed, SafeDemoPayload(Path("demo_blob/scripts"), launch_browser=False)), events)
    runner.client = SimpleNamespace(responses=FakeResponses([
        tool_response("one", "read", "read_product_blob", {"name": "products/product-001.txt"}),
        final_response(),
    ]))

    result = CatalogueService(database, feed, runner, events).process(source_name="products/product-001.txt")

    assert result == {"processed": 1, "created": 1}
    assert len(database.products()) == 1
    assert "PRODUCT_PUBLISHED" in [event["event_type"] for event in database.events()]


def test_explicit_source_selection_retries_an_already_published_product(tmp_path):
    config = settings(tmp_path, "vulnerable")
    database = Database(config.database_path)
    feed = LocalProductFeed(Path("demo_blob"))
    events = EventLogger(database)
    runner = AgentRunner(config, AgentTools(feed, SafeDemoPayload(Path("demo_blob/scripts"), launch_browser=False)), events)
    runner.client = SimpleNamespace(responses=FakeResponses([
        tool_response("one", "read-one", "read_product_blob", {"name": "products/product-001.txt"}),
        final_response(),
        tool_response("two", "read-two", "read_product_blob", {"name": "products/product-001.txt"}),
        final_response(),
    ]))
    service = CatalogueService(database, feed, runner, events)

    first = service.process(source_name="products/product-001.txt")
    retry = service.process(source_name="products/product-001.txt")

    assert first == {"processed": 1, "created": 1}
    assert retry == {"processed": 1, "created": 1}
    assert len(database.products()) == 1


def test_all_products_run_includes_an_already_published_poisoned_source(tmp_path):
    config = settings(tmp_path, "vulnerable")
    database = Database(config.database_path)
    database.add_product(PRODUCT, "products/product-016-poisoned.md")
    feed = LocalProductFeed(Path("demo_blob"))
    events = EventLogger(database)
    runner = RecordingRunner()
    service = CatalogueService(database, feed, runner, events)

    result = service.process(
        include_poisoned=True,
        retry_sources={"products/product-016-poisoned.md"},
    )

    assert result == {"processed": 4, "created": 0}
    assert runner.sources == [
        "products/product-001.txt",
        "products/product-002.md",
        "products/product-003.json",
        "products/product-016-poisoned.md",
    ]
