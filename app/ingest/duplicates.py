"""Exact and near-duplicate grouping.

- Exact: identical SHA-256 of file bytes.
- Near: perceptual hashes within a Hamming distance on BOTH pHash and dHash
  (resized/re-compressed copies, burst shots). Requiring two independent hashes
  to agree reduces false positives.
- Burst window (ADR-023): real camera bursts (~1s apart) showed, on the owner's real library,
  much more pHash noise across frames than dHash noise for the same true-duplicate pairs. Within
  ``burst_window_s`` of another photo's capture time, a looser pHash bound is used instead; dHash
  is always checked at the normal (strict) threshold. Outside that window the original strict
  pHash+dHash rule applies unchanged, which is what keeps unrelated-but-similar-looking photos
  (e.g. two separate visits to the same room) from merging.

Groups are connected components (union-find). Each group keeps one "best" photo; the rest are
alternates — they are never deleted, only de-prioritized. Best = among members whose technical
quality is within ``BEST_QUALITY_MARGIN`` of the group's top, the one with the most pixels (an
original beats its compressed/resized copy); then quality; then the lowest id (ADR-017).
If the user picked a keeper for the group (``picks``: content_hash -> time picked), their most
recent pick wins over the automatic choice; the automatic choice is still reported (ADR-018).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import numpy as np


# Quality differences below this are treated as noise when choosing a group's best photo.
BEST_QUALITY_MARGIN = 0.05


@dataclass
class DuplicateGroup:
    kind: str                 # exact | near
    member_ids: list[int]
    best_id: int              # effective keeper (user pick if any)
    auto_best_id: int = 0     # what the automatic rule chose


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _hex_array(values: list[str]) -> np.ndarray:
    return np.array([int(v, 16) for v in values], dtype=np.uint64)


def _capture_epochs(photos: list[dict]) -> np.ndarray:
    """Capture time as Unix epoch seconds, NaN where missing/unparseable (never matches a window)."""
    out = np.full(len(photos), np.nan)
    for i, p in enumerate(photos):
        ct = p.get("capture_time")
        if ct:
            try:
                out[i] = datetime.fromisoformat(ct).timestamp()
            except ValueError:
                pass
    return out


def choose_best(members: list[dict], margin: float = BEST_QUALITY_MARGIN) -> dict:
    top = max(m.get("quality_score") or 0.0 for m in members)
    close = [m for m in members if (m.get("quality_score") or 0.0) >= top - margin]
    return max(
        close,
        key=lambda m: ((m.get("width") or 0) * (m.get("height") or 0), m.get("quality_score") or 0.0, -m["id"]),
    )


def find_duplicate_groups(
    photos: list[dict],
    phash_threshold: int = 8,
    dhash_threshold: int = 12,
    picks: dict[str, str] | None = None,
    burst_window_s: float | None = None,
    burst_phash_threshold: int | None = None,
) -> list[DuplicateGroup]:
    """``photos``: dicts with id, content_hash, phash, dhash, quality_score, width, height, and
    optionally capture_time (ISO string) when ``burst_window_s``/``burst_phash_threshold`` are given
    (ADR-023; see module docstring)."""
    n = len(photos)
    if n < 2:
        return []
    uf = _UnionFind(n)

    by_hash: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(photos):
        if p.get("content_hash"):
            by_hash[p["content_hash"]].append(i)
    for idxs in by_hash.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)

    if phash_threshold >= 0:
        ph = _hex_array([p["phash"] for p in photos])
        dh = _hex_array([p["dhash"] for p in photos])
        use_burst = burst_window_s is not None and burst_phash_threshold is not None
        times = _capture_epochs(photos) if use_burst else None
        candidate_phash_threshold = max(phash_threshold, burst_phash_threshold) if use_burst else phash_threshold
        for i in range(n - 1):
            dp = np.bitwise_count(ph[i + 1:] ^ ph[i])
            cand = np.nonzero(dp <= candidate_phash_threshold)[0]
            if cand.size == 0:
                continue
            dd = np.bitwise_count(dh[i + 1 + cand] ^ dh[i])
            dhash_ok = dd <= dhash_threshold
            if not dhash_ok.any():
                continue
            dp_cand = dp[cand]
            if use_burst:
                dt = np.abs(times[i + 1 + cand] - times[i])
                in_burst = dt <= burst_window_s  # NaN (missing capture_time) compares False
                phash_ok = np.where(in_burst, dp_cand <= burst_phash_threshold, dp_cand <= phash_threshold)
            else:
                phash_ok = dp_cand <= phash_threshold
            for off in cand[dhash_ok & phash_ok]:
                uf.union(i, i + 1 + int(off))

    components: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        components[uf.find(i)].append(i)

    groups: list[DuplicateGroup] = []
    for idxs in components.values():
        if len(idxs) < 2:
            continue
        members = [photos[i] for i in idxs]
        kind = "exact" if len({m["content_hash"] for m in members}) == 1 else "near"
        auto = choose_best(members)
        picked = [m for m in members if picks and m.get("content_hash") in picks]
        best = max(picked, key=lambda m: (picks[m["content_hash"]], -m["id"])) if picked else auto
        groups.append(DuplicateGroup(kind=kind, member_ids=sorted(m["id"] for m in members), best_id=best["id"],
                                     auto_best_id=auto["id"]))
    groups.sort(key=lambda g: g.member_ids[0])
    return groups
