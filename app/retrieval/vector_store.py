"""Vector index abstraction (implemented in Milestone 2). Local first; replaceable later (e.g. pgvector)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, namespace: str, ids: Sequence[int], vectors: np.ndarray) -> None: ...

    @abstractmethod
    def search(self, namespace: str, query: np.ndarray, k: int, allowed_ids: Sequence[int] | None = None
               ) -> list[tuple[int, float]]: ...

    @abstractmethod
    def delete(self, namespace: str, ids: Sequence[int] | None = None) -> None: ...
