"""Deterministic technical-quality metrics (no ML model, no license concerns).

Sharpness uses the variance of the Laplacian computed per tile on a normalized-size
grayscale image, taking the 90th percentile across tiles. Using the sharpest tiles
(rather than the whole frame) avoids flagging shallow depth-of-field portraits —
where the background is intentionally blurred — as blurry.

These are heuristics; thresholds are configurable and must be calibrated with the
evaluation harness on real libraries.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from app.vision.interfaces import ImageQualityAnalyzer, QualityReport

TILE_GRID = 4


def laplacian(gray: np.ndarray) -> np.ndarray:
    g = gray
    return g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4.0 * g[1:-1, 1:-1]


def tile_sharpness(gray: np.ndarray, grid: int = TILE_GRID) -> float:
    lap = laplacian(gray)
    h, w = lap.shape
    if h < grid * 4 or w < grid * 4:
        return float(lap.var()) if lap.size else 0.0
    variances = [
        float(lap[i * h // grid:(i + 1) * h // grid, j * w // grid:(j + 1) * w // grid].var())
        for i in range(grid)
        for j in range(grid)
    ]
    return float(np.percentile(variances, 90))


def normalize_contrast(gray: np.ndarray) -> np.ndarray:
    """Stretch the 1st..99th luminance percentiles to 0..255 so dark or low-contrast
    (but in-focus) photos are not mistaken for blurry ones. Near-flat images are left as-is."""
    lo, hi = np.percentile(gray, [1, 99])
    if hi - lo < 8:
        return gray
    return (gray - lo) * (255.0 / (hi - lo))


# Exposure rules (luminance 0..255). Exposed so the review UI can show "value vs rule".
UNDEREXPOSED_MEAN = 45
UNDEREXPOSED_DARK_FRACTION = 0.65
OVEREXPOSED_MEAN = 225
OVEREXPOSED_BRIGHT_FRACTION = 0.45

# Weights of the technical quality score. Resolution is deliberately NOT part of it (ADR-017):
# whether a photo has enough pixels depends on the print size, which is judged per layout slot.
# The previous sharpness/exposure/contrast weights (0.5/0.2/0.1) are kept in the same proportion.
SCORE_WEIGHTS = {"sharpness": 0.625, "exposure": 0.25, "contrast": 0.125}


def exposure_issue_for(brightness: float, dark_fraction: float, bright_fraction: float) -> str | None:
    if brightness < UNDEREXPOSED_MEAN or dark_fraction > UNDEREXPOSED_DARK_FRACTION:
        return "underexposed"
    if brightness > OVEREXPOSED_MEAN or bright_fraction > OVEREXPOSED_BRIGHT_FRACTION:
        return "overexposed"
    return None


def quality_components(sharpness: float, exposure_issue: str | None, contrast: float) -> dict[str, float]:
    return {
        "sharpness": round(min(1.0, math.log10(1.0 + max(sharpness, 0.0)) / 3.0), 3),  # ~1000 -> 1.0
        "exposure": 1.0 if exposure_issue is None else 0.4,
        "contrast": round(min(1.0, max(contrast, 0.0) / 50.0), 3),
    }


def combined_quality_score(sharpness: float, exposure_issue: str | None, contrast: float) -> float:
    """Transparent technical score 0..1 from stored measurements (also used by the v3 migration)."""
    c = quality_components(sharpness, exposure_issue, contrast)
    return round(sum(SCORE_WEIGHTS[k] * c[k] for k in SCORE_WEIGHTS), 4)


class ClassicalQualityAnalyzer(ImageQualityAnalyzer):
    name = "classical-v2"

    def __init__(self, blur_threshold: float = 40.0, analysis_max_side: int = 1024):
        self.blur_threshold = blur_threshold
        self.analysis_max_side = analysis_max_side

    def analyze(self, image: Image.Image) -> QualityReport:
        gray_img = image.convert("L")
        if max(gray_img.size) > self.analysis_max_side:
            gray_img.thumbnail((self.analysis_max_side, self.analysis_max_side), Image.Resampling.BILINEAR)
        gray = np.asarray(gray_img, dtype=np.float32)

        sharpness = round(tile_sharpness(normalize_contrast(gray)), 2)
        brightness = float(gray.mean())
        contrast = round(float(gray.std()), 2)
        dark = float((gray < 16).mean())
        bright = float((gray > 245).mean())
        exposure_issue = exposure_issue_for(brightness, dark, bright)

        return QualityReport(
            sharpness=sharpness,
            brightness=round(brightness, 2),
            contrast=contrast,
            dark_fraction=round(dark, 4),
            bright_fraction=round(bright, 4),
            exposure_issue=exposure_issue,
            is_blurry=sharpness < self.blur_threshold,
            quality_score=combined_quality_score(sharpness, exposure_issue, contrast),
            components=quality_components(sharpness, exposure_issue, contrast),
        )
