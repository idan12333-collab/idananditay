from PIL import Image, ImageFilter

from app.ingest.analyzer import AnalyzeConfig, analyze_file, detect_screenshot
from app.ingest.duplicates import find_duplicate_groups
from app.ingest.hashing import hamming, perceptual_hashes, sha256_file
from app.vision.quality.classical import ClassicalQualityAnalyzer
from tests.fixtures import scene


def test_sha256_identical_for_copies(library):
    _, p = library
    assert sha256_file(p["a"]) == sha256_file(p["a_copy"])
    assert sha256_file(p["a"]) != sha256_file(p["a_small"])


def test_perceptual_hash_near_vs_different(library):
    _, p = library
    with Image.open(p["a"]) as a, Image.open(p["a_small"]) as s, Image.open(p["b"]) as b:
        ha, hs, hb = perceptual_hashes(a.convert("RGB")), perceptual_hashes(s.convert("RGB")), perceptual_hashes(b.convert("RGB"))
    assert hamming(ha[0], hs[0]) <= 4 and hamming(ha[1], hs[1]) <= 6
    assert hamming(ha[0], hb[0]) > 16


def test_blur_detection_separates_sharp_and_blurry():
    analyzer = ClassicalQualityAnalyzer(blur_threshold=40)
    sharp = scene(20)
    blurry = sharp.filter(ImageFilter.GaussianBlur(10))
    r_sharp, r_blurry = analyzer.analyze(sharp), analyzer.analyze(blurry)
    assert r_sharp.sharpness > 10 * r_blurry.sharpness
    assert not r_sharp.is_blurry and r_blurry.is_blurry
    assert r_sharp.quality_score > r_blurry.quality_score
    assert set(r_sharp.components) == {"sharpness", "exposure", "contrast"}


def test_shallow_depth_of_field_is_not_blurry():
    """Sharp subject + blurred background should not be flagged (tile-based metric)."""
    img = scene(21).filter(ImageFilter.GaussianBlur(10))
    subject = scene(22, size=(350, 250))
    img.paste(subject, (500, 380))
    assert not ClassicalQualityAnalyzer(blur_threshold=40).analyze(img).is_blurry


def test_dark_but_sharp_is_not_blurry():
    import numpy as np

    dark = Image.fromarray((np.asarray(scene(23), dtype=np.float32) * 0.08).astype(np.uint8))
    report = ClassicalQualityAnalyzer(blur_threshold=40).analyze(dark)
    assert report.exposure_issue == "underexposed" and not report.is_blurry


def test_exposure_flags():
    analyzer = ClassicalQualityAnalyzer()
    dark = Image.new("RGB", (400, 300), (5, 5, 5))
    bright = Image.new("RGB", (400, 300), (252, 252, 252))
    assert analyzer.analyze(dark).exposure_issue == "underexposed"
    assert analyzer.analyze(bright).exposure_issue == "overexposed"
    assert analyzer.analyze(scene(3)).exposure_issue is None


def test_detect_screenshot():
    assert detect_screenshot("Screenshot_2023.png", "PNG", False, 100, 100)[0]
    assert detect_screenshot("צילום מסך 2023.png", "PNG", False, 100, 100)[0]
    assert detect_screenshot("x.png", "PNG", False, 1170, 2532)[0]
    assert not detect_screenshot("x.png", "PNG", True, 1170, 2532)[0]  # has camera EXIF
    # Desktop-monitor sizes are common real JPEG/video-frame dimensions too -> JPEG stays untouched.
    assert not detect_screenshot("IMG_1.jpg", "JPEG", False, 1920, 1080)[0]


def test_detect_screenshot_jpeg_phone_size():
    """Regression: real false negatives found on the owner's library (2026-09-27) — JPEG
    screenshots at an exact phone-screen resolution with no camera EXIF (ADR-023)."""
    assert detect_screenshot("IMG_7004.JPG", "JPEG", False, 1290, 2796)[0]
    assert detect_screenshot("IMG_6382.JPG", "JPEG", False, 1290, 2796)[0]
    assert not detect_screenshot("IMG_1.JPG", "JPEG", True, 1290, 2796)[0]  # has camera EXIF
    # Swapped (landscape) order is not checked for JPEG -> must NOT be flagged (see analyzer.py).
    assert not detect_screenshot("IMG_1.JPG", "JPEG", False, 2796, 1290)[0]


def test_analyze_file_handles_orientation_and_errors(library, tmp_path):
    _, p = library
    cfg = AnalyzeConfig(thumbnails_dir=str(tmp_path / "thumbs"))
    r = analyze_file(str(p["rotated"]), cfg)
    assert r["status"] == "ok"
    assert (r["width"], r["height"]) == (900, 1200) and r["orientation"] == 6
    thumb = tmp_path / "thumbs" / r["thumbnail_path"]
    with Image.open(thumb) as t:
        assert t.height > t.width  # thumbnail is upright
        assert max(t.size) == cfg.thumbnail_size

    bad = analyze_file(str(p["corrupt"]), cfg)
    assert bad["status"] == "error" and bad["error"]

    missing = analyze_file(str(tmp_path / "nope.jpg"), cfg)
    assert missing["status"] == "error"


def _cand(i, ch, ph, dh, q=0.5, w=100, h=100, capture_time=None):
    return {
        "id": i, "content_hash": ch, "phash": ph, "dhash": dh, "quality_score": q, "width": w, "height": h,
        "capture_time": capture_time,
    }


def test_duplicate_grouping_logic():
    photos = [
        _cand(1, "h1", "ffffffffffffffff", "0000000000000000", q=0.5),
        _cand(2, "h1", "ffffffffffffffff", "0000000000000000", q=0.5),  # exact dup of 1
        _cand(3, "h3", "fffffffffffffff0", "0000000000000001", q=0.9),  # near dup of 1 (better)
        _cand(4, "h4", "0000000000000000", "ffffffffffffffff"),          # unrelated
        _cand(5, "h5", "00000000000000ff", "ffffffffffff0000"),          # phash close to 4, dhash far
        _cand(6, "h6", "0f0f0f0f0f0f0f0f", "f0f0f0f0f0f0f0f0"),          # unrelated
        _cand(7, "h6", "0f0f0f0f0f0f0f0f", "f0f0f0f0f0f0f0f0", w=200),   # exact dup of 6
    ]
    groups = find_duplicate_groups(photos, phash_threshold=8, dhash_threshold=12)
    assert len(groups) == 2
    g1, g2 = groups
    assert g1.member_ids == [1, 2, 3] and g1.kind == "near" and g1.best_id == 3
    assert g2.member_ids == [6, 7] and g2.kind == "exact"
    assert g2.best_id == 7  # tie on quality -> higher resolution


def test_duplicate_grouping_empty_and_single():
    assert find_duplicate_groups([]) == []
    assert find_duplicate_groups([_cand(1, "a", "ff", "ff")]) == []


def test_duplicate_grouping_burst_window_merges_noisy_phash():
    """Regression (ADR-023): real ~1s-apart bursts had dHash agreeing but pHash Hamming distance
    well above the strict threshold. A capture-time-adjacent pair should still group when dHash
    is tight, using the looser burst pHash bound; the same pHash gap far apart in time must not."""
    photos = [
        _cand(1, "h1", "0000000000000000", "0000000000000000", capture_time="2026-01-01T10:00:00"),
        # 1s later, same burst: dHash close (agrees), pHash far apart under the strict threshold.
        _cand(2, "h2", "00000000000fffff", "0000000000000003", capture_time="2026-01-01T10:00:01"),
        # Same pHash distance from photo 1 (20 bits, disjoint from photo 2's bits so it also can't
        # accidentally match photo 2) and a close dHash too, but capture time is hours away ->
        # must NOT merge even though the hash gap alone looks just like the real burst above.
        _cand(3, "h3", "fffff00000000000", "0000000000000003", capture_time="2026-01-01T14:00:00"),
    ]
    groups = find_duplicate_groups(
        photos, phash_threshold=8, dhash_threshold=12, burst_window_s=3.0, burst_phash_threshold=28
    )
    assert len(groups) == 1
    assert groups[0].member_ids == [1, 2]


def test_duplicate_grouping_burst_window_disabled_by_default():
    """Without burst args (e.g. old callers), behavior is unchanged: strict thresholds everywhere."""
    photos = [
        _cand(1, "h1", "0000000000000000", "0000000000000000", capture_time="2026-01-01T10:00:00"),
        _cand(2, "h2", "00000000000fffff", "0000000000000003", capture_time="2026-01-01T10:00:01"),
    ]
    assert find_duplicate_groups(photos, phash_threshold=8, dhash_threshold=12) == []


def test_duplicate_grouping_burst_window_ignores_missing_capture_time():
    """No capture_time on either side -> never treated as in-burst; strict threshold still applies."""
    photos = [
        _cand(1, "h1", "0000000000000000", "0000000000000000"),
        _cand(2, "h2", "00000000000fffff", "0000000000000003"),
    ]
    groups = find_duplicate_groups(
        photos, phash_threshold=8, dhash_threshold=12, burst_window_s=3.0, burst_phash_threshold=28
    )
    assert groups == []
