from __future__ import annotations

from pathlib import Path

from .base import BlobObject, ProductFeed


class LocalProductFeed(ProductFeed):
    def __init__(self, root: Path):
        self.root = root

    def list_objects(self) -> list[BlobObject]:
        products = self.root / "products"
        return [BlobObject(path.relative_to(self.root).as_posix()) for path in sorted(products.iterdir()) if path.is_file()]

    def read_object(self, name: str) -> str:
        root = self.root.resolve()
        candidate = (self.root / name).resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise FileNotFoundError(name)
        return candidate.read_text(encoding="utf-8")
