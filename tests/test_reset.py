import json
from pathlib import Path

import app.main as main
from app.database import Database
from app.services.demo_payload import SafeDemoPayload
from app.services.events import EventLogger


PRODUCT = {
    "id": "demo-1",
    "name": "Demo Sensor",
    "manufacturer": "Fictional Systems",
    "category": "Sensor",
    "short_description": "A demo product.",
    "long_description": "A product used to verify reset behavior.",
    "features": ["Safe"],
    "technical_specs": {"Range": "Demo"},
    "tags": ["demo"],
}


def prepare_state(monkeypatch, tmp_path):
    database = Database(str(tmp_path / "reset.db"))
    payload = SafeDemoPayload(Path("demo_blob/scripts"), launch_browser=False)
    monkeypatch.setattr(main, "database", database)
    monkeypatch.setattr(main, "events", EventLogger(database))
    monkeypatch.setattr(main, "payload", payload)
    monkeypatch.setattr(main, "INITIAL_SECURITY_MODE", "vulnerable")
    monkeypatch.setattr(main, "INITIAL_STORAGE_MODE", "local")
    monkeypatch.setattr(main, "run_state", {
        "running": False,
        "reset_pending": False,
        "reset_version": 0,
        "last_reset_at": None,
        "last_result": {"processed": 1},
        "last_error": "recording failed",
    })
    database.add_product(PRODUCT, "products/product-001.txt")
    EventLogger(database).log("PRODUCT_PUBLISHED", "Demo Sensor")
    payload.launch_fake_ransomware_demo()
    main.settings.agent_security_mode = "protected"
    return database, payload


def test_reset_restores_complete_initial_state(monkeypatch, tmp_path):
    database, payload = prepare_state(monkeypatch, tmp_path)

    result = main.api_reset()

    assert result["ok"] and not result["pending"]
    assert database.products() == []
    assert database.events() == []
    assert not payload.state.active
    assert main.settings.agent_security_mode == "vulnerable"
    assert main.run_state["reset_version"] == 1
    assert main.run_state["last_result"] is None
    assert main.run_state["last_error"] is None


def test_reset_queues_safely_during_active_run(monkeypatch, tmp_path):
    database, _payload = prepare_state(monkeypatch, tmp_path)
    main.run_state["running"] = True

    response = main.api_reset()

    assert response.status_code == 202
    assert json.loads(response.body)["pending"] is True
    assert main.run_state["reset_pending"] is True
    assert main.stop_event.is_set()
    assert database.products()

    main._perform_reset()
    assert database.products() == []
    assert not main.run_state["reset_pending"]
    assert not main.stop_event.is_set()
