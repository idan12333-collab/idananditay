"""Print suitability is derived from pixels per print size, never a single megapixel cutoff (ADR-017)."""

import pytest

from app.core.config import Settings
from app.ingest.duplicates import choose_best
from app.printing.suitability import PrintPolicy, PrintSize, assess, effective_ppi, max_size_cm
from app.vision.quality.classical import SCORE_WEIGHTS, combined_quality_score

POLICY = PrintPolicy()  # 300 / 200 / 150 PPI, smallest slot 6x9 cm


def _level(assessment, label):
    return next(s for s in assessment["sizes"] if s["label"] == label)


def test_effective_ppi_uses_the_limiting_side_and_best_orientation():
    # 20x30 cm = 7.87x11.81 in. A 12 MP phone photo: long 4032/11.81 = 341, short 3024/7.87 = 384 -> 341.
    assert round(effective_ppi(4032, 3024, PrintSize(20, 30))) == 341
    # Orientation of the photo does not matter: the slot is rotated to match.
    assert effective_ppi(3024, 4032, PrintSize(20, 30)) == effective_ppi(4032, 3024, PrintSize(20, 30))
    assert effective_ppi(0, 100, PrintSize(10, 15)) == 0.0


def test_levels_for_a_typical_phone_photo():
    a = assess(4032, 3024, POLICY)
    assert _level(a, "20×30 cm")["level"] == "excellent"
    assert _level(a, "30×30 cm")["level"] == "good"  # 3024 px / 11.81 in = 256 PPI
    assert a["extremely_low"] is False
    assert a["largest_reference_size"]["excellent"] == "20×30 cm"
    assert a["largest_reference_size"]["good"] == "30×30 cm"


def test_one_megapixel_photo_is_fine_as_a_small_photo():
    """Flagged 'low resolution' by the old 1 MP rule; actually fine at small album sizes."""
    a = assess(1024, 768, POLICY)
    assert a["extremely_low"] is False
    assert _level(a, "6×9 cm")["level"] == "good"  # 1024 px / 3.54 in = 289 PPI
    assert _level(a, "10×15 cm")["level"] == "acceptable"
    assert _level(a, "30×30 cm")["level"] == "poor"  # but not a full page
    assert a["max_size_cm"]["good"] == max_size_cm(1024, 768, 200) == (13.0, 9.8)


def test_only_extremely_small_images_get_the_strong_warning():
    # 6x9 cm at 150 PPI needs 532 x 355 px (long x short).
    assert POLICY.extreme_low_res_pixels() == (532, 355)
    assert POLICY.is_extremely_low(160, 120)       # the thumbnail-sized files found in the owner's library
    assert POLICY.is_extremely_low(531, 355)
    assert POLICY.is_extremely_low(355, 531)
    assert not POLICY.is_extremely_low(532, 355)
    assert not POLICY.is_extremely_low(355, 532)   # portrait
    assert not POLICY.is_extremely_low(899, 1600)  # smallest real photo in the owner's library


def test_min_slot_and_levels_are_configurable():
    small_slots = PrintPolicy(min_slot=PrintSize(4, 6))
    assert POLICY.is_extremely_low(400, 300)
    assert not small_slots.is_extremely_low(400, 300)

    settings = Settings(_env_file=None, print_min_slot_cm=(4, 6), print_good_ppi=250,
                        print_reference_sizes_cm=[(10, 15)])
    policy = settings.print_policy()
    assert policy.min_slot.label == "4×6 cm" and policy.good_ppi == 250
    assert [s["label"] for s in assess(3000, 2000, policy)["sizes"]] == ["10×15 cm"]

    with pytest.raises(ValueError):
        PrintPolicy(excellent_ppi=150, good_ppi=200, acceptable_ppi=100)


def test_assess_handles_missing_dimensions():
    assert assess(None, None, POLICY) is None
    assert assess(0, 100, POLICY) is None


def test_quality_score_does_not_depend_on_resolution():
    assert "resolution" not in SCORE_WEIGHTS
    assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 1e-9
    assert combined_quality_score(1000, None, 50) == 1.0
    assert combined_quality_score(1000, "underexposed", 50) < combined_quality_score(1000, None, 50)


def _m(i, q, w, h):
    return {"id": i, "quality_score": q, "width": w, "height": h}


def test_duplicate_best_prefers_larger_copy_when_quality_is_similar():
    original, whatsapp_copy = _m(1, 0.80, 4032, 3024), _m(2, 0.83, 1600, 1200)
    assert choose_best([whatsapp_copy, original])["id"] == 1
    # A clearly sharper photo still wins over a bigger but worse one.
    assert choose_best([_m(3, 0.60, 4032, 3024), _m(4, 0.90, 1600, 1200)])["id"] == 4
    # Full tie -> lowest id.
    assert choose_best([_m(6, 0.5, 100, 100), _m(5, 0.5, 100, 100)])["id"] == 5
