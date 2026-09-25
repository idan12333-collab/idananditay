"""Album rendering and print-provider abstractions (implemented in Milestones 6, 8, 9).

The internal album model stays provider-neutral; a print vendor is an adapter only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class AlbumRenderer(ABC):
    @abstractmethod
    def render_preview(self, album_project: dict, out_dir: Path) -> Path: ...

    @abstractmethod
    def export_pdf(self, album_project: dict, print_profile: dict, out_path: Path) -> Path: ...


@dataclass
class PrintProviderCapabilities:
    """Not every provider supports every operation; capabilities must be explicit."""
    list_products: bool = False
    quotes: bool = False
    order_submission: bool = False
    order_status: bool = False
    notes: list[str] = field(default_factory=list)


class PrintProvider(ABC):
    capabilities: PrintProviderCapabilities

    @abstractmethod
    def list_products(self) -> list[dict]: ...

    @abstractmethod
    def get_print_profile(self, product_id: str) -> dict: ...

    @abstractmethod
    def validate_album(self, album_project: dict, product_id: str) -> list[str]: ...
