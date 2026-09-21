from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import Database
from app.services.demo_payload import SafeDemoPayload

if __name__ == "__main__":
    Database(settings.database_path).clear()
    SafeDemoPayload(settings.demo_blob_path / "scripts").reset()
    print("Demo state reset; source files were preserved.")
