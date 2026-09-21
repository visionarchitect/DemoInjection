from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import Database

if __name__ == "__main__":
    Database(settings.database_path)
    print(f"Demo feed ready at {settings.demo_blob_path}")
