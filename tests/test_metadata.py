from datetime import datetime

from PIL import Image

from app.ingest.metadata import (
    date_from_filename,
    dms_to_decimal,
    extract_metadata,
    parse_exif_datetime,
    resolve_capture_time,
)


def test_parse_exif_datetime_variants():
    assert parse_exif_datetime("2019:05:12 10:00:00") == datetime(2019, 5, 12, 10, 0, 0)
    assert parse_exif_datetime(b"2019:05:12 10:00:00\x00") == datetime(2019, 5, 12, 10, 0, 0)
    assert parse_exif_datetime("2019-05-12 10:00:00") == datetime(2019, 5, 12, 10, 0, 0)
    assert parse_exif_datetime("0000:00:00 00:00:00") is None
    assert parse_exif_datetime("garbage") is None
    assert parse_exif_datetime("1800:01:01 00:00:00") is None
    assert parse_exif_datetime(None) is None


def test_date_from_filename():
    assert date_from_filename("IMG_20190512_101112.jpg") == datetime(2019, 5, 12, 10, 11, 12)
    assert date_from_filename("IMG-20190512-WA0001.jpg") == datetime(2019, 5, 12)
    assert date_from_filename("2021-03-04 10.11.12.jpg") == datetime(2021, 3, 4, 10, 11, 12)
    assert date_from_filename("PXL_20210304_101112345.jpg") == datetime(2021, 3, 4, 10, 11, 12)
    assert date_from_filename("DSC01234.jpg") is None
    assert date_from_filename("IMG_20191345.jpg") is None  # invalid month


def test_dms_to_decimal():
    assert abs(dms_to_decimal((35, 40, 34.32), "N") - 35.6762) < 1e-4
    assert abs(dms_to_decimal(((139, 1), (39, 1), (108, 100)), "E") - 139.6503) < 1e-4
    assert dms_to_decimal((33, 0, 0), "S") == -33.0
    assert dms_to_decimal(("x", 0, 0), "N") is None


def test_extract_metadata_from_fixture(library):
    _, paths = library
    with Image.open(paths["a"]) as im:
        meta = extract_metadata(im.getexif())
    assert meta.exif_time == datetime(2019, 5, 12, 10, 0, 0)
    assert meta.camera_make == "TestCam" and meta.camera_model == "X100"
    assert abs(meta.gps_lat - 35.6762) < 1e-3 and abs(meta.gps_lon - 139.6503) < 1e-3


def test_capture_time_priority(library):
    _, paths = library
    with Image.open(paths["named"]) as im:
        meta = extract_metadata(im.getexif())
    dt, src = resolve_capture_time(meta, paths["named"].name, paths["named"].stat().st_mtime)
    assert (dt, src) == (datetime(2021, 3, 4, 10, 11, 12), "filename")

    with Image.open(paths["b"]) as im:
        meta = extract_metadata(im.getexif())
    dt, src = resolve_capture_time(meta, "b.png", paths["b"].stat().st_mtime)
    assert src == "file_mtime" and dt is not None
