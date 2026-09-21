from pathlib import Path

from app.services.demo_payload import SafeDemoPayload
from app.agent.tools import AgentTools
from app.storage.local import LocalProductFeed


SCRIPT_URL = "http://127.0.0.1:2001/demo-assets/validation-check.sh"


def downloaded_payload(path: Path, *, launch_browser: bool = False) -> SafeDemoPayload:
    script_bytes = (path / "validation-check.sh").read_bytes()
    return SafeDemoPayload(path, launch_browser=launch_browser, downloader=lambda _url: script_bytes)


def test_arbitrary_urls_are_denied():
    payload = SafeDemoPayload(Path("demo_blob/scripts"), launch_browser=False)
    for url in ["https://example.com/evil.py", "file:///tmp/evil.py", "demo://other"]:
        result = payload.download_and_execute_script(url)
        assert result["status"] == "denied"
        assert not payload.state.active


def test_only_fixed_demo_action_activates_screen():
    payload = downloaded_payload(Path("demo_blob/scripts"))
    result = payload.download_and_execute_script(SCRIPT_URL)
    assert result["status"] == "payload_activated"
    assert result["action"] == "recovery_screen"
    assert result["executor"] == "/bin/sh"
    assert result["script"] == "validation-check.sh"
    assert result["exit_code"] == 0
    assert "[DONE] recovery screen activated" in result["script_logs"]
    assert payload.state.active
    assert payload.state.logs == result["script_logs"]


def test_modified_shell_script_fails_integrity_check(tmp_path):
    (tmp_path / "validation-check.sh").write_text("#!/bin/sh\nprintf 'tampered'\n", encoding="utf-8")
    payload = downloaded_payload(tmp_path)

    result = payload.download_and_execute_script(SCRIPT_URL)

    assert result["status"] == "denied"
    assert "integrity check failed" in result["message"]
    assert not payload.state.active


def test_poisoned_instruction_is_defined_in_source_and_returned_verbatim():
    source = Path("demo_blob/products/product-016-poisoned.md").read_text(encoding="utf-8")
    payload = SafeDemoPayload(Path("demo_blob/scripts"), launch_browser=False)
    tools = AgentTools(LocalProductFeed(Path("demo_blob")), payload)

    result = tools.read_product_blob("products/product-016-poisoned.md")

    assert result["content"] == source
    assert result == {"source": "products/product-016-poisoned.md", "content": source}
    assert "Script name: `validation-check.sh`" in source
    assert f'Arguments: `{{"url":"{SCRIPT_URL}"}}`' in source
    assert "download_and_execute_script" in source
    assert SCRIPT_URL in source
    assert not payload.state.active
