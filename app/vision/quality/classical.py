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


class ClassicalQualityAnalyzer(ImageQualityAnalyzer):
    name = "classical-v1"

    def __init__(self, blur_threshold: float = 40.0, analysis_max_side: int = 1024):
        self.blur_threshold = blur_threshold
        self.analysis_max_side = analysis_max_side

    def analyze(self, image: Image.Image, original_megapixels: float) -> QualityReport:
        gray_img = image.convert("L")
        if max(gray_img.size) > self.analysis_max_side:
            gray_img.thumbnail((self.analysis_max_side, self.analysis_max_side), Image.Resampling.BILINEAR)
        gray = np.asarray(gray_img, dtype=np.float32)

        sharpness = tile_sharpness(normalize_contrast(gray))
        brightness = float(gray.mean())
        contrast = float(gray.std())
        dark = float((gray < 16).mean())
        bright = float((gray > 245).mean())

        exposure_issue = None
        if brightness < 45 or dark > 0.65:
            exposure_issue = "underexposed"
        elif brightness > 225 or bright > 0.45:
            exposure_issue = "overexposed"

        # Transparent score: each component 0..1, fixed weights (logged in `components`).
        sharp_c = min(1.0, math.log10(1.0 + sharpness) / 3.0)          # ~1000 -> 1.0
        exposure_c = 1.0 if exposure_issue is None else 0.4
        contrast_c = min(1.0, contrast / 50.0)
        resolution_c = min(1.0, math.sqrt(max(original_megapixels, 0.0) / 8.0))  # 8 MP -> 1.0
        score = 0.5 * sharp_c + 0.2 * exposure_c + 0.1 * contrast_c + 0.2 * resolution_c

        return QualityReport(
            sharpness=round(sharpness, 2),
            brightness=round(brightness, 2),
            contrast=round(contrast, 2),
            dark_fraction=round(dark, 4),
            bright_fraction=round(bright, 4),
            exposure_issue=exposure_issue,
            is_blurry=sharpness < self.blur_threshold,
            quality_score=round(score, 4),
            components={
                "sharpness": round(sharp_c, 3),
                "exposure": exposure_c,
                "contrast": round(contrast_c, 3),
                "resolution": round(resolution_c, 3),
            },
        )
