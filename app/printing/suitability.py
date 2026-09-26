"""Print suitability derived from native pixel dimensions (ADR-017).

Resolution is not a property of a photo alone: it depends on how large the photo is printed.
The measure is *effective PPI* = image pixels / printed inches. A photo that is too small for a
full page can be perfect in a small slot, so nothing here rejects or excludes a photo — it only
describes which print sizes it supports. The final authority is the per-slot check at layout /
export time (the user may also crop), using the chosen print provider's specification.

All numbers (PPI levels, reference sizes, smallest slot) are configurable starting defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CM_PER_INCH = 2.54

# Ordered best -> worst. "poor" = below the acceptable level at that size.
LEVELS = ("excellent", "good", "acceptable", "poor")


@dataclass(frozen=True)
class PrintSize:
    w_cm: float
    h_cm: float

    @property
    def label(self) -> str:
        return f"{self.w_cm:g}×{self.h_cm:g} cm"

    @property
    def long_short_in(self) -> tuple[float, float]:
        a, b = self.w_cm / CM_PER_INCH, self.h_cm / CM_PER_INCH
        return max(a, b), min(a, b)


DEFAULT_REFERENCE_SIZES: tuple[PrintSize, ...] = (
    PrintSize(6, 9), PrintSize(10, 15), PrintSize(13, 18), PrintSize(15, 20), PrintSize(20, 30), PrintSize(30, 30),
)


@dataclass(frozen=True)
class PrintPolicy:
    excellent_ppi: float = 300.0
    good_ppi: float = 200.0
    acceptable_ppi: float = 150.0
    reference_sizes: tuple[PrintSize, ...] = DEFAULT_REFERENCE_SIZES
    # Smallest slot a layout is expected to offer. A photo that cannot reach acceptable_ppi even here
    # gets the one strong warning ("extremely low resolution"). Configurable: future layouts may
    # have smaller slots.
    min_slot: PrintSize = field(default_factory=lambda: PrintSize(6, 9))

    def __post_init__(self) -> None:
        if not (self.excellent_ppi >= self.good_ppi >= self.acceptable_ppi > 0):
            raise ValueError("PPI levels must satisfy excellent >= good >= acceptable > 0")

    def level(self, ppi: float) -> str:
        if ppi >= self.excellent_ppi:
            return "excellent"
        if ppi >= self.good_ppi:
            return "good"
        if ppi >= self.acceptable_ppi:
            return "acceptable"
        return "poor"

    def extreme_low_res_pixels(self) -> tuple[int, int]:
        """(long, short) pixel sides needed to fill ``min_slot`` at the acceptable level."""
        long_in, short_in = self.min_slot.long_short_in
        return _ceil(long_in * self.acceptable_ppi), _ceil(short_in * self.acceptable_ppi)

    def is_extremely_low(self, width: int, height: int) -> bool:
        need_long, need_short = self.extreme_low_res_pixels()
        return max(width, height) < need_long or min(width, height) < need_short

    def to_dict(self) -> dict:
        return {
            "levels_ppi": {"excellent": self.excellent_ppi, "good": self.good_ppi, "acceptable": self.acceptable_ppi},
            "reference_sizes": [s.label for s in self.reference_sizes],
            "min_slot": self.min_slot.label,
        }


def _ceil(x: float) -> int:
    # Round away float noise (e.g. 531.0000001) before taking the ceiling.
    r = round(x, 6)
    return int(r) if r == int(r) else int(r) + 1


def effective_ppi(width: int, height: int, size: PrintSize) -> float:
    """PPI when the photo fills ``size`` (excess cropped), slot rotated to match the photo.

    Pairing the photo's long side with the slot's long side is always the better orientation.
    """
    if width <= 0 or height <= 0:
        return 0.0
    long_in, short_in = size.long_short_in
    return min(max(width, height) / long_in, min(width, height) / short_in)


def max_size_cm(width: int, height: int, ppi: float) -> tuple[float, float]:
    """Largest print (same aspect ratio as the photo, no crop) that still reaches ``ppi``."""
    return round(width / ppi * CM_PER_INCH, 1), round(height / ppi * CM_PER_INCH, 1)


def assess(width: int | None, height: int | None, policy: PrintPolicy) -> dict | None:
    """Everything the UI/curation needs to know about printing this photo. Pure function."""
    if not width or not height:
        return None
    sizes = []
    largest_by_level: dict[str, str | None] = {"excellent": None, "good": None, "acceptable": None}
    for s in sorted(policy.reference_sizes, key=lambda s: s.w_cm * s.h_cm):
        ppi = effective_ppi(width, height, s)
        lvl = policy.level(ppi)
        sizes.append({"label": s.label, "w_cm": s.w_cm, "h_cm": s.h_cm, "ppi": round(ppi), "level": lvl})
        for name in largest_by_level:
            if LEVELS.index(lvl) <= LEVELS.index(name):
                largest_by_level[name] = s.label
    return {
        "width": width,
        "height": height,
        "megapixels": round(width * height / 1_000_000, 2),
        "max_size_cm": {
            "excellent": max_size_cm(width, height, policy.excellent_ppi),
            "good": max_size_cm(width, height, policy.good_ppi),
            "acceptable": max_size_cm(width, height, policy.acceptable_ppi),
        },
        "largest_reference_size": largest_by_level,
        "sizes": sizes,
        "extremely_low": policy.is_extremely_low(width, height),
        "policy": policy.to_dict(),
    }
