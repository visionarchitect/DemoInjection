from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator


class Database:
    def __init__(self, path: str):
        self.path = path
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, manufacturer TEXT NOT NULL,
                category TEXT NOT NULL, short_description TEXT NOT NULL,
                long_description TEXT NOT NULL, features_json TEXT NOT NULL,
                technical_specs_json TEXT NOT NULL, tags_json TEXT NOT NULL, source_name TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL,
                tool_name TEXT, tool_arguments TEXT, source_name TEXT, source_trust TEXT,
                details_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS demo_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    def clear(self) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM products")
            db.execute("DELETE FROM agent_events")
            db.execute("DELETE FROM demo_state")

    def clear_events(self) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM agent_events")

    def add_product(self, product: dict[str, Any], source_name: str) -> None:
        with self.connection() as db:
            db.execute("""INSERT OR REPLACE INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                product["id"], product["name"], product["manufacturer"], product["category"],
                product["short_description"], product["long_description"], json.dumps(product["features"]),
                json.dumps(product["technical_specs"]), json.dumps(product["tags"]), source_name,
            ))

    def products(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM products ORDER BY id").fetchall()
        return [self._product_row(row) for row in rows]

    def product(self, product_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return self._product_row(row) if row else None

    def processed_sources(self) -> set[str]:
        with self.connection() as db:
            rows = db.execute("SELECT source_name FROM products WHERE source_name IS NOT NULL").fetchall()
        return {row["source_name"] for row in rows}

    @staticmethod
    def _product_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["features"] = json.loads(item.pop("features_json"))
        item["technical_specs"] = json.loads(item.pop("technical_specs_json"))
        item["tags"] = json.loads(item.pop("tags_json"))
        return item

    def add_event(self, event: dict[str, Any]) -> None:
        with self.connection() as db:
            db.execute("""INSERT INTO agent_events (timestamp, event_type, severity, message, tool_name, tool_arguments, source_name, source_trust, details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                event["timestamp"], event["event_type"], event["severity"], event["message"], event.get("tool_name"),
                json.dumps(event.get("tool_arguments")) if event.get("tool_arguments") is not None else None,
                event.get("source_name"), event.get("source_trust"), json.dumps(event.get("details", {})),
            ))

    def events(self, after_id: int = 0) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM agent_events WHERE id > ? ORDER BY id", (after_id,)).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            event = dict(row)
            event["tool_arguments"] = json.loads(event["tool_arguments"]) if event["tool_arguments"] else None
            event["details"] = json.loads(event.pop("details_json"))
            events.append(event)
        return events
