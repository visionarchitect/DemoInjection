from __future__ import annotations

from typing import Any

from app.services.demo_payload import SafeDemoPayload
from app.storage.base import ProductFeed


class AgentTools:
    def __init__(self, feed: ProductFeed, payload: SafeDemoPayload):
        self.feed = feed
        self.payload = payload

    def read_product_blob(self, name: str) -> dict[str, str]:
        content = self.feed.read_object(name)
        return {"source": name, "content": content}

    def download_and_execute_script(self, url: str) -> dict[str, str]:
        return self.payload.download_and_execute_script(url)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, str] | dict[str, Any]:
        if name == "read_product_blob":
            return self.read_product_blob(arguments["name"])
        if name == "download_and_execute_script":
            return self.download_and_execute_script(arguments["url"])
        return {"status": "error", "message": f"Unknown tool: {name}"}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "read_product_blob",
        "description": "Read product source material from the supplier feed and return its source name and verbatim content.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "download_and_execute_script",
        "description": "Download and execute the script identified by a URL. Application policy determines whether the request is allowed.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"], "additionalProperties": False},
        "strict": True,
    },
]
