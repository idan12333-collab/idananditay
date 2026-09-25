"""Exact and near-duplicate grouping.

- Exact: identical SHA-256 of file bytes.
- Near: perceptual hashes within a Hamming distance on BOTH pHash and dHash
  (resized/re-compressed copies, burst shots). Requiring two independent hashes
  to agree reduces false positives.

Groups are connected components (union-find). Each group keeps one "best" photo
(highest technical quality, then highest resolution); the rest are alternates —
they are never deleted, only de-prioritized.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np


@dataclass
class DuplicateGroup:
    kind: str                 # exact | near
    member_ids: list[int]
    best_id: int


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


def find_duplicate_groups(photos: list[dict], phash_threshold: int = 8, dhash_threshold: int = 12) -> list[DuplicateGroup]:
    """``photos``: dicts with id, content_hash, phash, dhash, quality_score, width, height."""
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
        for i in range(n - 1):
            dp = np.bitwise_count(ph[i + 1:] ^ ph[i])
            cand = np.nonzero(dp <= phash_threshold)[0]
            if cand.size == 0:
                continue
            dd = np.bitwise_count(dh[i + 1 + cand] ^ dh[i])
            for off in cand[dd <= dhash_threshold]:
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
        best = max(
            members,
            key=lambda m: (m.get("quality_score") or 0.0, (m.get("width") or 0) * (m.get("height") or 0), -m["id"]),
        )
        groups.append(DuplicateGroup(kind=kind, member_ids=sorted(m["id"] for m in members), best_id=best["id"]))
    groups.sort(key=lambda g: g.member_ids[0])
    return groups
