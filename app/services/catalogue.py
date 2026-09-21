from __future__ import annotations

from app.agent.runner import AgentRunner
from app.database import Database
from app.services.events import EventLogger
from app.storage.base import ProductFeed
from collections.abc import Callable


class CatalogueService:
    def __init__(self, database: Database, feed: ProductFeed, runner: AgentRunner, events: EventLogger):
        self.database = database
        self.feed = feed
        self.runner = runner
        self.events = events

    def process(
        self,
        limit: int | None = None,
        source_name: str | None = None,
        include_poisoned: bool = True,
        retry_sources: set[str] | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        objects = self.feed.list_objects()
        processed_sources = self.database.processed_sources()
        retry_sources = retry_sources or set()
        selected = [
            item for item in objects
            if (source_name is None or item.name == source_name)
            and (include_poisoned or item.name != "products/product-016-poisoned.md")
            # Explicit selections and named retry sources are deliberate
            # retries. Other bulk-run products already published are skipped.
            and (source_name is not None or item.name in retry_sources or item.name not in processed_sources)
        ]
        if limit is not None:
            selected = selected[:limit]
        created = 0
        processed = 0
        for item in selected:
            if stop_requested and stop_requested():
                self.events.log("AGENT_COMPLETED", "Agent stopped by presenter.", "warning", source_name=item.name)
                break
            self.events.log("SOURCE_DISCOVERED", item.name, "info", source_name=item.name, source_trust="external_untrusted")
            product = self.runner.process(item.name)
            processed += 1
            if product:
                self.database.add_product(product.model_dump(), item.name)
                self.events.log("PRODUCT_PUBLISHED", product.name, "success", source_name=item.name, source_trust="external_untrusted")
                created += 1
        self.events.log("AGENT_COMPLETED", f"Processed {processed} source object(s); created {created} product(s).", "success")
        return {"processed": processed, "created": created}
