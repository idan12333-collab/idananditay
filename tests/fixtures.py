"""Synthetic fixture photos (generated, so no personal data is committed)."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from PIL.TiffImagePlugin import IFDRational


def scene(seed: int, size=(1400, 1000)) -> Image.Image:
    """Textured, photo-like image: gradient + random shapes + fine noise. Distinct per seed."""
    rng = np.random.default_rng(seed)
    w, h = size
    x = np.linspace(0, 1, w)[None, :]
    y = np.linspace(0, 1, h)[:, None]
    channels = [
        255 * (0.3 + 0.5 * x * rng.random() + 0.2 * y),
        255 * (0.2 + 0.6 * y * rng.random()),
        255 * (0.5 + 0.4 * (1 - x) * rng.random()),
    ]
    base = np.stack([np.broadcast_to(c, (h, w)) for c in channels], axis=-1)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    for _ in range(25):
        x0, y0 = rng.integers(0, w - 50), rng.integers(0, h - 50)
        x1, y1 = x0 + rng.integers(40, w // 3), y0 + rng.integers(40, h // 3)
        color = tuple(int(c) for c in rng.integers(0, 255, 3))
        (draw.ellipse if rng.random() < 0.5 else draw.rectangle)([x0, y0, x1, y1], fill=color, outline=(0, 0, 0), width=3)
    noise = rng.normal(0, 6, (h, w, 3))
    arr = np.clip(np.asarray(img, dtype=np.float32) + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def exif_bytes(dt: str | None = None, make: str | None = None, model: str | None = None,
               orientation: int | None = None, gps: tuple[float, float] | None = None) -> bytes:
    exif = Image.Exif()
    if make:
        exif[0x010F] = make
    if model:
        exif[0x0110] = model
    if orientation:
        exif[0x0112] = orientation
    if dt:
        exif.get_ifd(0x8769)[0x9003] = dt
    if gps:
        def dms(v: float):
            v = abs(v)
            d = int(v)
            m = int((v - d) * 60)
            s = round((v - d - m / 60) * 3600, 2)
            return (IFDRational(d, 1), IFDRational(m, 1), IFDRational(int(s * 100), 100))
        g = exif.get_ifd(0x8825)
        g[1] = "N" if gps[0] >= 0 else "S"
        g[2] = dms(gps[0])
        g[3] = "E" if gps[1] >= 0 else "W"
        g[4] = dms(gps[1])
    return exif.tobytes()


def build_library(root: Path) -> dict[str, Path]:
    """Creates a small library covering every Milestone 1 case. Returns name -> path."""
    root.mkdir(parents=True, exist_ok=True)
    sub = root / "2019" / "טיול"  # Hebrew folder name on purpose
    sub.mkdir(parents=True)
    paths: dict[str, Path] = {}

    a = scene(1)
    paths["a"] = root / "a.jpg"
    a.save(paths["a"], quality=92, exif=exif_bytes("2019:05:12 10:00:00", "TestCam", "X100", gps=(35.6762, 139.6503)))

    paths["a_copy"] = sub / "a_copy.jpg"  # exact duplicate
    shutil.copyfile(paths["a"], paths["a_copy"])

    paths["a_small"] = sub / "a_small.jpg"  # near duplicate: resized + recompressed
    a.resize((840, 600), Image.Resampling.LANCZOS).save(paths["a_small"], quality=70)

    paths["b"] = root / "b.png"
    scene(2).save(paths["b"])

    paths["blurry"] = root / "blurry.jpg"
    scene(4).filter(ImageFilter.GaussianBlur(10)).save(
        paths["blurry"], quality=90, exif=exif_bytes("2020:01:01 12:00:00", "TestCam")
    )

    paths["tiny"] = root / "tiny.jpg"
    scene(5, size=(320, 240)).save(paths["tiny"], quality=90, exif=exif_bytes("2021:06:01 09:00:00", "TestCam"))

    paths["rotated"] = root / "rotated.jpg"  # stored landscape, displayed portrait
    scene(6, size=(1200, 900)).save(paths["rotated"], quality=90,
                                    exif=exif_bytes("2022:02:02 08:00:00", "TestCam", orientation=6))

    paths["named"] = root / "IMG_20210304_101112.jpg"  # date only in the filename
    scene(7).save(paths["named"], quality=90)

    paths["screenshot"] = root / "Screenshot_2023-01-01.png"
    scene(8, size=(1170, 2532)).save(paths["screenshot"])

    paths["dark"] = root / "dark.jpg"
    Image.fromarray((np.asarray(scene(9), dtype=np.float32) * 0.08).astype(np.uint8)).save(
        paths["dark"], quality=90, exif=exif_bytes("2020:07:07 21:00:00", "TestCam")
    )

    paths["corrupt"] = root / "corrupt.jpg"
    good = (root / "a.jpg").read_bytes()
    paths["corrupt"].write_bytes(good[: len(good) // 3])

    (root / "notes.txt").write_text("not a photo")
    hidden = root / ".hidden"
    hidden.mkdir()
    scene(10).save(hidden / "ignored.jpg")
    return paths
