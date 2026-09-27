"""Seed sample for the owner's quick labeling (ADR-022, evaluation/SEED_WORKER_BRIEF.md).

A fixed, deterministic sample of one library: ~150 kept photos stratified by capture month, ~70
filtered photos spread over the filter's primary reasons, ~15 whole duplicate groups (picked in the
existing side-by-side view, not labeled 1/2/3), plus photos the owner nominates ("★ חשובה").
The sample file holds the owner's photo IDs/hashes, so it lives in the app data dir, never in git.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.db.repository import Repository

SAMPLE_VERSION = 1
DEFAULT_SEED = 20260926
KEPT_TARGET = 150
FILTERED_TARGET = 70
FILTERED_MIN_PER_REASON = 10
FILTERED_REASONS = ("duplicate", "screenshot", "low_quality", "exposure")
DUP_GROUPS_TARGET = 15
LABELED_STRATA = ("random_kept", "filtered", "nominated")  # shown in the 1/2/3 screen; dup_groups is not


def is_held_out(content_hash: str) -> bool:
    """~30% of items are never used for tuning; deterministic from the content hash."""
    return int(content_hash[:8], 16) % 10 < 3


def sample_path(data_dir: Path, library_id: int) -> Path:
    return Path(data_dir) / "seed" / f"seed_sample_lib{library_id}.json"


def original_exists(photo: dict) -> bool:
    """The file may have been moved/replaced since the last scan; such photos can't be shown."""
    return bool(photo.get("source_path")) and Path(photo["source_path"]).is_file()


def _all(repo: Repository, library_id: int, filter_name: str) -> list[dict]:
    items, _ = repo.list_photos(library_id, filter_name, sort="path", limit=1_000_000)
    return [p for p in items if p.get("content_hash") and original_exists(p)]


def _allocate(sizes: dict[str, int], target: int, minimum: int) -> dict[str, int]:
    """Proportional allocation over buckets with a per-bucket minimum (capped by bucket size).

    Largest-remainder rounding; leftover capacity is redistributed so the total reaches
    min(target, sum(sizes)). If the minimums alone exceed the target, the biggest buckets win.
    """
    total = sum(sizes.values())
    target = min(target, total)
    keys = sorted(sizes, key=lambda k: (-sizes[k], k))
    alloc = {k: 0 for k in sizes}
    budget = target
    for k in keys:  # minimums first
        take = min(minimum, sizes[k], budget)
        alloc[k] = take
        budget -= take
    while budget > 0:
        room = {k: sizes[k] - alloc[k] for k in keys if sizes[k] > alloc[k]}
        if not room:
            break
        pool = sum(room.values())
        shares = {k: budget * room[k] / pool for k in room}
        add = {k: int(shares[k]) for k in room}
        rest = budget - sum(add.values())
        for k in sorted(room, key=lambda k: (-(shares[k] - add[k]), k))[:rest]:
            add[k] += 1
        for k, n in add.items():
            n = min(n, room[k])
            alloc[k] += n
            budget -= n
    return alloc


def build_sample(repo: Repository, library_id: int, seed: int = DEFAULT_SEED, *,
                 kept_target: int = KEPT_TARGET, filtered_target: int = FILTERED_TARGET,
                 dup_groups_target: int = DUP_GROUPS_TARGET) -> dict:
    """The sample for one library. Never fails on a small library: short strata are reported."""
    rng = random.Random(seed)
    used: set[str] = set()
    items: list[dict] = []
    shortfall: dict[str, str] = {}

    def add(p: dict, stratum: str, **extra) -> None:
        used.add(p["content_hash"])
        items.append({"content_hash": p["content_hash"], "photo_id": p["id"], "stratum": stratum,
                      "held_out": int(is_held_out(p["content_hash"])), **extra})

    # 1. whole duplicate groups (members with a hash; groups of >= 2)
    groups, _ = repo.list_duplicate_groups(library_id, 0, 1_000_000)
    candidates = []
    for g in sorted(groups, key=lambda g: g["id"]):
        members = [m for m in g["members"] if m.get("content_hash") and m.get("status") == "ok" and original_exists(m)]
        if len(members) >= 2:
            candidates.append((g["id"], members))
    chosen_groups = rng.sample(candidates, min(dup_groups_target, len(candidates)))
    dup_items: list[dict] = []
    for gid, members in sorted(chosen_groups, key=lambda c: c[0]):
        for m in members:
            if m["content_hash"] not in used:
                used.add(m["content_hash"])
                dup_items.append({"content_hash": m["content_hash"], "photo_id": m["id"], "stratum": "dup_groups",
                                  "held_out": int(is_held_out(m["content_hash"])), "group_id": gid})
    if len(chosen_groups) < dup_groups_target:
        shortfall["dup_groups"] = f"{len(chosen_groups)}/{dup_groups_target} groups"

    def unique(photos: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out = []
        for p in photos:
            h = p["content_hash"]
            if h not in used and h not in seen:
                seen.add(h)
                out.append(p)
        return out

    # 2. kept photos, stratified by capture year-month
    kept = unique(_all(repo, library_id, "kept"))
    by_month: dict[str, list[dict]] = defaultdict(list)
    for p in kept:
        by_month[(p.get("capture_time") or "")[:7] or "unknown"].append(p)
    alloc = _allocate({k: len(v) for k, v in by_month.items()}, kept_target, 1)
    for month in sorted(by_month):
        for p in rng.sample(by_month[month], alloc[month]):
            add(p, "random_kept")
    n_kept = sum(alloc.values())
    if n_kept < kept_target:
        shortfall["random_kept"] = f"{n_kept}/{kept_target}"

    # 3. filtered photos, spread over the primary reasons
    by_reason = {r: unique(_all(repo, library_id, f"reason_{r}")) for r in FILTERED_REASONS}
    alloc = _allocate({r: len(v) for r, v in by_reason.items()}, filtered_target, FILTERED_MIN_PER_REASON)
    reason_counts = {}
    for r in FILTERED_REASONS:
        picked = rng.sample(by_reason[r], alloc[r])
        for p in picked:
            add(p, "filtered", reason=r)
        reason_counts[r] = len(picked)
    n_filtered = sum(reason_counts.values())
    if n_filtered < filtered_target:
        shortfall["filtered"] = f"{n_filtered}/{filtered_target}"

    # Mixed order, so the owner doesn't label all kept photos first and then all filtered ones.
    rng.shuffle(items)
    items.extend(dup_items)
    return {
        "version": SAMPLE_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "library_id": library_id,
        "seed": seed,
        "counts": {"random_kept": n_kept, "filtered": n_filtered, "filtered_by_reason": reason_counts,
                   "dup_groups": len(chosen_groups), "dup_group_photos": len(dup_items)},
        "shortfall": shortfall,
        "items": items,
    }


def load_sample(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def save_sample(path: Path, sample: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash never leaves a half-written sample


def nominate(sample: dict, photo: dict) -> bool:
    """Add a photo to the `nominated` stratum. False if it is already in the sample."""
    if any(it["content_hash"] == photo["content_hash"] for it in sample["items"]):
        return False
    sample["items"].append({"content_hash": photo["content_hash"], "photo_id": photo["id"], "stratum": "nominated",
                            "held_out": int(is_held_out(photo["content_hash"]))})
    return True
