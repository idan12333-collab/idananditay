"""Provider interfaces for all vision/AI capabilities (see ADR-002).

Business logic depends only on these abstractions. Concrete adapters live in
sub-packages (``embeddings/``, ``faces/``, ``quality/``, ``aesthetics/``) and every
model-backed adapter must be registered in MODEL_REGISTRY.md with its license status.

Only ``ImageQualityAnalyzer`` has an implementation in Milestone 1 (classical, no model).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from PIL import Image


@dataclass
class QualityReport:
    sharpness: float                 # higher = sharper (tile-wise Laplacian variance, p90)
    brightness: float                # mean luminance 0..255
    contrast: float                  # luminance std-dev
    dark_fraction: float             # share of near-black pixels
    bright_fraction: float           # share of near-white pixels
    exposure_issue: str | None       # underexposed | overexposed | None
    is_blurry: bool
    quality_score: float             # 0..1, transparent combination of sharpness/exposure/contrast
    components: dict[str, float] = field(default_factory=dict)


class ImageQualityAnalyzer(ABC):
    """Technical (not aesthetic) quality: blur, exposure, contrast.

    Resolution is not a quality signal here: print suitability depends on the print size and is
    handled by ``app.printing.suitability`` (ADR-017).
    """

    name: str

    @abstractmethod
    def analyze(self, image: Image.Image) -> QualityReport: ...


@dataclass
class FaceDetection:
    bbox: tuple[float, float, float, float]  # x, y, w, h — normalized 0..1
    confidence: float
    embedding: np.ndarray | None = None


class ImageEmbeddingProvider(ABC):
    """Joint image/text embedding space for natural-language retrieval (Milestone 2)."""

    name: str
    dimension: int

    @abstractmethod
    def embed_images(self, images: Sequence[Image.Image]) -> np.ndarray: ...

    @abstractmethod
    def embed_text(self, texts: Sequence[str]) -> np.ndarray: ...


class FaceEmbeddingProvider(ABC):
    """Face detection + identity embeddings (Milestone 3). Never used to name unknown people."""

    name: str

    @abstractmethod
    def detect_and_embed(self, image: Image.Image) -> list[FaceDetection]: ...


class AestheticScorer(ABC):
    """Aesthetic appeal 0..1 (Milestone 5). One ranking signal among many, never the only one."""

    name: str

    @abstractmethod
    def score(self, images: Sequence[Image.Image]) -> list[float]: ...


class CaptionOrVisionProvider(ABC):
    """Optional enrichment (captions/tags). External providers require an explicit product decision."""

    name: str
    sends_data_off_device: bool

    @abstractmethod
    def describe(self, image: Image.Image) -> dict: ...
