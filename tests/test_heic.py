import pytest

from app.ingest.analyzer import AnalyzeConfig, analyze_file
from app.ingest.imaging import HEIC_SUPPORTED
from tests.fixtures import exif_bytes, scene

pytestmark = pytest.mark.skipif(not HEIC_SUPPORTED, reason="pillow-heif not installed")


def test_heic_is_decoded_with_metadata(tmp_path):
    path = tmp_path / "IMG_0001.HEIC"
    try:
        scene(30, size=(1200, 900)).save(path, format="HEIF", quality=80,
                                         exif=exif_bytes("2024:08:15 18:30:00", "Apple", "iPhone"))
    except Exception as exc:  # encoder not available in this build
        pytest.skip(f"cannot encode HEIC here: {exc}")
    r = analyze_file(str(path), AnalyzeConfig(thumbnails_dir=str(tmp_path / "t")))
    assert r["status"] == "ok", r.get("error")
    assert r["format"] == "HEIF"
    assert (r["width"], r["height"]) == (1200, 900)
    assert r["capture_time"] == "2024-08-15T18:30:00" and r["camera_make"] == "Apple"
    assert (tmp_path / "t" / r["thumbnail_path"]).is_file()
