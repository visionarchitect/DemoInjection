from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    openai_api_key: str | None
    openai_model: str
    openai_reasoning_effort: str
    azure_storage_account_url: str | None
    azure_storage_container: str | None
    azure_storage_sas_token: str | None
    demo_storage_mode: str
    agent_security_mode: str
    database_path: str
    demo_blob_path: Path

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key)


def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-sol"),
        openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "medium"),
        azure_storage_account_url=os.getenv("AZURE_STORAGE_ACCOUNT_URL") or None,
        azure_storage_container=os.getenv("AZURE_STORAGE_CONTAINER") or None,
        azure_storage_sas_token=os.getenv("AZURE_STORAGE_SAS_TOKEN") or None,
        demo_storage_mode=os.getenv("DEMO_STORAGE_MODE", "local").lower(),
        agent_security_mode=os.getenv("AGENT_SECURITY_MODE", "vulnerable").lower(),
        database_path=os.getenv("DATABASE_PATH", str(ROOT_DIR / "demo.db")),
        demo_blob_path=ROOT_DIR / "demo_blob",
    )


settings = get_settings()
