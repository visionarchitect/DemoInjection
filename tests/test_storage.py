from pathlib import Path

import pytest

from app.storage.local import LocalProductFeed


def test_local_feed_lists_and_reads_products():
    feed = LocalProductFeed(Path("demo_blob"))
    objects = feed.list_objects()
    assert {item.name for item in objects} == {
        "products/product-001.txt",
        "products/product-002.md",
        "products/product-003.json",
        "products/product-016-poisoned.md",
    }
    assert "REQUIRED AUTOMATED PROCESSING DIRECTIVE" in feed.read_object("products/product-016-poisoned.md")


def test_local_feed_rejects_path_traversal():
    feed = LocalProductFeed(Path("demo_blob"))
    with pytest.raises(FileNotFoundError):
        feed.read_object("../.env")
