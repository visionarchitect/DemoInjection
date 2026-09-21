from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class BlobObject:
    name: str


class ProductFeed(ABC):
    @abstractmethod
    def list_objects(self) -> list[BlobObject]:
        raise NotImplementedError

    @abstractmethod
    def read_object(self, name: str) -> str:
        raise NotImplementedError
