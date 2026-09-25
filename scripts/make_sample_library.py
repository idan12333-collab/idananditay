"""Generate a synthetic photo library for demos and benchmarks (no personal data).

Usage:
    python scripts/make_sample_library.py OUT_DIR --count 1000 --width 4000 --height 3000

Creates year/month folders with EXIF dates, some GPS, burst sequences (near duplicates),
exact copies, blurry, dark, low-res, screenshots and a corrupted file.
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

from tests.fixtures import exif_bytes, scene  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--count", type=int, default=300)
    ap.add_argument("--width", type=int, default=3000)
    ap.add_argument("--height", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    start = datetime(2018, 3, 1, 9, 0, 0)
    made = 0
    last_path: Path | None = None
    while made < args.count:
        when = start + timedelta(days=rng.uniform(0, 8.5 * 365), seconds=rng.randint(0, 43200))
        folder = args.out / f"{when:%Y}" / f"{when:%m}"
        folder.mkdir(parents=True, exist_ok=True)
        kind = rng.random()
        base = scene(rng.randint(0, 10**9), size=(args.width, args.height))
        gps = (35.68 + rng.uniform(-0.1, 0.1), 139.69 + rng.uniform(-0.1, 0.1)) if rng.random() < 0.3 else None

        if kind < 0.08 and made + 3 <= args.count:  # burst of 3 near-identical shots
            for i in range(3):
                shot = base.rotate(rng.uniform(-0.6, 0.6), resample=Image.Resampling.BILINEAR)
                p = folder / f"IMG_{when:%Y%m%d_%H%M%S}_{i}.jpg"
                shot.save(p, quality=88, exif=exif_bytes(f"{when + timedelta(seconds=i):%Y:%m:%d %H:%M:%S}", "SampleCam", gps=gps))
                made += 1
            continue
        if kind < 0.12 and last_path is not None:  # exact copy
            shutil.copyfile(last_path, folder / f"copy_{made}_{last_path.name}")
            made += 1
            continue
        if kind < 0.17:
            base = base.filter(ImageFilter.GaussianBlur(9))
        elif kind < 0.21:
            base = Image.fromarray((np.asarray(base, dtype=np.float32) * 0.1).astype(np.uint8))
        elif kind < 0.24:
            base = base.resize((640, 480))
        elif kind < 0.26:
            p = folder / f"Screenshot_{when:%Y%m%d-%H%M%S}.png"
            scene(rng.randint(0, 10**9), size=(1170, 2532)).save(p)
            made += 1
            continue
        p = folder / f"IMG_{when:%Y%m%d_%H%M%S}_{made}.jpg"
        base.save(p, quality=88, exif=exif_bytes(f"{when:%Y:%m:%d %H:%M:%S}", "SampleCam", gps=gps))
        last_path = p
        made += 1

    if last_path is not None:
        data = last_path.read_bytes()
        (args.out / "corrupted.jpg").write_bytes(data[: len(data) // 4])
    print(f"Created {made} photos (+1 corrupted) in {args.out}")


if __name__ == "__main__":
    main()
