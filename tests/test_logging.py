from app.database import Database
from app.services.events import EventLogger


def test_event_storage_does_not_store_secret_values(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    logger = EventLogger(database)
    logger.log("MODEL_REQUEST", "request rejected for sk-message-secret-12345678", details={"openai_api_key": "sk-never-store-this", "nested": {"sas_token": "secret-sas"}})
    event = database.events()[0]
    assert "sk-never-store-this" not in str(event)
    assert "secret-sas" not in str(event)
    assert "sk-message-secret-12345678" not in str(event)
    assert str(event).count("[REDACTED]") == 3


def test_clear_events_removes_history(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    EventLogger(database).log("MODEL_REQUEST", "hello")
    assert len(database.events()) == 1
    database.clear_events()
    assert database.events() == []
