"""Curation evaluation metrics (EVAL_PLAN.md): the owner's curation labels vs. the filter.

Read-only: the DB is opened with ``mode=ro``; nothing in the app database is ever written.
The filter definitions are imported from ``app.db.repository`` so "filtered" means exactly what the
app shows.

Two filter views are measured:
- **auto**: the automatic filter alone (the thing under test in round 0);
- **effective**: after the owner's technical corrections (review_labels / duplicate picks).

Usage:
    python -m evaluation.metrics --library 14 [--db PATH] [--out evaluation/reports]

Writes ``round0_<date>.md`` (aggregates + photo IDs, safe to commit) and
``local/round0_<date>_failures.csv`` (with file names; git-ignored, never commit).
"""

from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from app.core.config import Settings
from app.db.repository import AUTO_FLAGS, PHOTO_FILTERS

WORTH = ("must", "maybe", "no")
TECH_REASONS = ("screenshot", "low_quality", "exposure")


# ----------------------------------------------------------------------------- stats
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for k successes out of n (None when n == 0)."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass
class Rate:
    k: int
    n: int

    @property
    def value(self) -> float | None:
        return self.k / self.n if self.n else None

    def fmt(self) -> str:
        if not self.n:
            return "n/a (n=0)"
        lo, hi = wilson(self.k, self.n)  # type: ignore[misc]
        return f"{self.k}/{self.n} = {self.k / self.n:.1%} (95% CI {lo:.0%}–{hi:.0%})"


# ----------------------------------------------------------------------------- data
def auto_reason(p: dict) -> str | None:
    """The automatic filter's primary reason, same precedence as the app's review screen."""
    if p["f_duplicate"]:
        return "duplicate"
    if p["f_screenshot"]:
        return "screenshot"
    if p["f_blurry"] or p["f_extreme_low_res"]:
        return "low_quality"
    if p["f_exposure"]:
        return "exposure"
    return None


def connect_ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_labeled(conn: sqlite3.Connection, library_id: int, sql_params: dict) -> tuple[list[dict], int]:
    """One row per labeled photo (lowest id per content_hash), plus the count of orphan labels."""
    flags = ", ".join(f"({v.format(**sql_params)}) AS f_{k}" for k, v in AUTO_FLAGS.items())
    eff = PHOTO_FILTERS["filtered"].format(**sql_params)
    rows = conn.execute(
        f"SELECT photos.id, photos.rel_path, photos.duplicate_group_id, photos.is_group_best, {flags}, "
        f"({eff}) AS eff_filtered, "
        "cl.worthiness, cl.special, cl.held_out, cl.stratum "
        "FROM curation_labels cl JOIN photos ON photos.content_hash = cl.content_hash "
        "WHERE photos.library_id = ? AND photos.status = 'ok' AND photos.id = ("
        "  SELECT MIN(q.id) FROM photos q WHERE q.library_id = photos.library_id "
        "  AND q.status = 'ok' AND q.content_hash = photos.content_hash)",
        (library_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["auto_reason"] = auto_reason(d)
        d["auto_filtered"] = d["auto_reason"] is not None
        d["eff_filtered"] = bool(d["eff_filtered"])
        out.append(d)
    orphans = conn.execute(
        "SELECT COUNT(*) FROM curation_labels cl WHERE NOT EXISTS (SELECT 1 FROM photos p "
        "WHERE p.content_hash = cl.content_hash AND p.library_id = ? AND p.status = 'ok')",
        (library_id,),
    ).fetchone()[0]
    return out, orphans


# ----------------------------------------------------------------------------- metrics
@dataclass
class Metrics:
    n: int
    m1_false_exclusion_must: Rate
    m1_false_exclusion_must_maybe: Rate
    m2_special_lost: Rate
    m3_candidate_recall: Rate
    m4_junk_retention: Rate
    by_reason: dict[str, Counter] = field(default_factory=dict)


def compute(rows: list[dict], view: str = "auto") -> Metrics:
    """Candidate-stage metrics on the labeled rows.

    A photo is "technically excluded" when the filter removes it for a technical reason
    (screenshot / low quality / exposure / owner-bad). Duplicate alternates are NOT counted as
    lost: their group keeps one copy, so the moment survives. Copy choice is measured by M5.
    """
    def excluded(r: dict) -> bool:
        if view == "auto":
            return r["auto_reason"] in TECH_REASONS
        return r["eff_filtered"] and r["auto_reason"] != "duplicate"

    def reaches_ranking(r: dict) -> bool:  # kept, or represented by its duplicate keeper
        return not excluded(r)

    must = [r for r in rows if r["worthiness"] == "must"]
    wanted = [r for r in rows if r["worthiness"] in ("must", "maybe")]
    special = [r for r in rows if r["special"] and r["worthiness"] != "no"]
    junk = [r for r in rows if r["worthiness"] == "no"]
    by_reason: dict[str, Counter] = {}
    for r in rows:
        by_reason.setdefault(r["auto_reason"] or "kept", Counter())[r["worthiness"]] += 1
    return Metrics(
        n=len(rows),
        m1_false_exclusion_must=Rate(sum(map(excluded, must)), len(must)),
        m1_false_exclusion_must_maybe=Rate(sum(map(excluded, wanted)), len(wanted)),
        m2_special_lost=Rate(sum(map(excluded, special)), len(special)),
        m3_candidate_recall=Rate(sum(map(reaches_ranking, wanted)), len(wanted)),
        m4_junk_retention=Rate(sum(r["auto_reason"] is None if view == "auto" else not r["eff_filtered"]
                                   for r in junk), len(junk)),
        by_reason=by_reason,
    )


def duplicate_agreement(conn: sqlite3.Connection, library_id: int, rows: list[dict]) -> dict:
    """M5: how often the automatic keeper matches the owner.

    Evidence: (a) groups where the owner changed the pick; (b) groups where the automatic keeper is
    labeled "no" while another copy is labeled must/maybe (a label-based disagreement).
    """
    groups = conn.execute(
        "SELECT id, best_photo_id, auto_best_photo_id FROM duplicate_groups WHERE library_id = ?", (library_id,)
    ).fetchall()
    changed = [g["id"] for g in groups if g["auto_best_photo_id"] is not None and g["best_photo_id"] != g["auto_best_photo_id"]]
    by_group: dict[int, list[dict]] = {}
    for r in rows:
        if r["duplicate_group_id"] is not None:
            by_group.setdefault(r["duplicate_group_id"], []).append(r)
    auto_best = {g["id"]: g["auto_best_photo_id"] for g in groups}
    conflicts = []
    for gid, members in by_group.items():
        keeper = next((m for m in members if m["id"] == auto_best.get(gid)), None)
        if keeper and keeper["worthiness"] == "no" and any(m["worthiness"] != "no" for m in members if m is not keeper):
            conflicts.append(gid)
    return {"groups": len(groups), "owner_changed": changed, "labeled_groups": len(by_group), "label_conflicts": conflicts}


def runtime_per_1000(conn: sqlite3.Connection, library_id: int) -> float | None:
    """M8: seconds per 1,000 photos for the latest completed ingest job of this library."""
    j = conn.execute(
        "SELECT total, started_at, finished_at FROM jobs WHERE library_id = ? AND kind = 'ingest' "
        "AND status = 'done' AND total > 0 ORDER BY started_at DESC LIMIT 1", (library_id,)
    ).fetchone()
    if not j or not j["started_at"] or not j["finished_at"]:
        return None
    secs = (datetime.fromisoformat(j["finished_at"]) - datetime.fromisoformat(j["started_at"])).total_seconds()
    return secs / j["total"] * 1000


def failures(rows: list[dict], dup: dict) -> list[dict]:
    """The failure-mode log (EVAL_PLAN.md), automatic-filter view."""
    out = []
    for r in rows:
        kinds = []
        if r["auto_reason"] in TECH_REASONS and r["worthiness"] != "no":
            kinds.append("moment_missed" if r["special"] else "wrongly_excluded")
        if r["auto_reason"] is None and r["worthiness"] == "no":
            kinds.append("junk_retained")
        if r["duplicate_group_id"] in set(dup["label_conflicts"]) | set(dup["owner_changed"]) and not r["auto_filtered"]:
            kinds.append("wrong_duplicate")
        for k in kinds:
            out.append({"kind": k, "photo_id": r["id"], "rel_path": r["rel_path"], "worthiness": r["worthiness"],
                        "special": r["special"], "auto_reason": r["auto_reason"] or "kept",
                        "effective": "filtered" if r["eff_filtered"] else "kept",
                        "stratum": r["stratum"], "held_out": r["held_out"]})
    order = {"moment_missed": 0, "wrongly_excluded": 1, "wrong_duplicate": 2, "junk_retained": 3}
    return sorted(out, key=lambda f: (order[f["kind"]], f["photo_id"]))


# ----------------------------------------------------------------------------- report
def _metric_rows(label: str, parts: dict[str, Metrics]) -> list[str]:
    lines = [f"| Metric | " + " | ".join(parts) + " |", "|---|" + "---|" * len(parts)]
    for key, name in (
        ("m1_false_exclusion_must", "M1 false exclusion (must)"),
        ("m1_false_exclusion_must_maybe", "M1b false exclusion (must+maybe)"),
        ("m2_special_lost", "M2 special moments lost (target 0)"),
        ("m3_candidate_recall", "M3 candidate recall (must+maybe)"),
        ("m4_junk_retention", "M4 junk retention (no)"),
    ):
        lines.append(f"| {name} | " + " | ".join(getattr(m, key).fmt() for m in parts.values()) + " |")
    return [f"### {label}", ""] + lines + [""]


def build_report(library_id: int, rows: list[dict], orphans: int, dup: dict, runtime: float | None,
                 fails: list[dict], today: str) -> str:
    split = {"all": rows, "tuning": [r for r in rows if not r["held_out"]], "held-out": [r for r in rows if r["held_out"]]}
    L = [
        f"# Curation evaluation: round 0 baseline ({today})",
        "",
        f"Library {library_id}. Filter under test: the M1 technical filter (classical rules). "
        "Labels: the owner's quick seed labels (curation_labels, ADR-022; blind, no AI suggestions).",
        f"Labeled photos measured: **{len(rows)}** (orphan labels without a photo: {orphans}). "
        f"Strata: {dict(Counter(r['stratum'] for r in rows))}. "
        f"Labels: {dict(Counter(r['worthiness'] for r in rows))}, special: {sum(bool(r['special']) for r in rows)}.",
        "",
        "Definitions: *excluded* = removed for a technical reason (screenshot / low quality / exposure). "
        "Duplicate alternates are not counted as lost (the group keeps one copy); copy choice is M5. "
        "Rates are over the labeled sample. The `filtered` stratum is over-sampled, so the rates are NOT "
        "library-wide rates; the per-reason table is the unbiased view per reason.",
        "",
        "## Headline (automatic filter)",
        "",
    ]
    L += _metric_rows("Automatic filter: all / tuning / held-out", {k: compute(v, "auto") for k, v in split.items()})
    L += _metric_rows("Effective filter (after the owner's technical corrections), all",
                      {"all": compute(rows, "effective")})
    L += ["## Per automatic reason: what the owner thinks of the photos it removed", "",
          "| Auto reason | n | must | maybe | no | wanted share (must+maybe) |", "|---|---|---|---|---|---|"]
    for reason, c in sorted(compute(rows).by_reason.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        L.append(f"| {reason} | {n} | {c['must']} | {c['maybe']} | {c['no']} | {Rate(c['must'] + c['maybe'], n).fmt()} |")
    L += ["", "## M5 duplicates", "",
          f"Duplicate groups: {dup['groups']}. Owner changed the automatic keeper in {len(dup['owner_changed'])} "
          f"group(s) {dup['owner_changed']}. Groups with labeled members: {dup['labeled_groups']}; "
          f"keeper labeled 'no' while another copy is wanted: {len(dup['label_conflicts'])} {dup['label_conflicts']}. "
          "The seed has no dup_groups stratum, so M5 is **not measurable yet** (n too small).", "",
          "## M8 runtime", "",
          (f"Last completed ingest: **{runtime:.0f} s / 1,000 photos** (real library, owner PC)."
           if runtime is not None else "No completed ingest job found."), "",
          "## Failure-mode log (automatic filter)", "",
          f"Counts: {dict(Counter(f['kind'] for f in fails))}. File names: `reports/local/` (git-ignored).", "",
          "| kind | photo id | label | special | auto reason | effective now | stratum | held-out |",
          "|---|---|---|---|---|---|---|---|"]
    for f in fails:
        L.append(f"| {f['kind']} | {f['photo_id']} | {f['worthiness']} | {f['special']} | {f['auto_reason']} | "
                 f"{f['effective']} | {f['stratum']} | {f['held_out']} |")
    contradictions = [r["id"] for r in rows if r["special"] and r["worthiness"] == "no"]
    if contradictions:
        L += ["", f"Label check: special=1 with worthiness=no on photo(s) {contradictions}; ask the owner to confirm."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--library", type=int, required=True)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "reports")
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args(argv)
    settings = Settings()
    long_px, short_px = settings.print_policy().extreme_low_res_pixels()
    conn = connect_ro(a.db or settings.db_path)
    try:
        rows, orphans = load_labeled(conn, a.library, {"long_px": long_px, "short_px": short_px})
        dup = duplicate_agreement(conn, a.library, rows)
        runtime = runtime_per_1000(conn, a.library)
    finally:
        conn.close()
    fails = failures(rows, dup)
    (a.out / "local").mkdir(parents=True, exist_ok=True)
    report = a.out / f"round0_{a.date}.md"
    report.write_text(build_report(a.library, rows, orphans, dup, runtime, fails, a.date), encoding="utf-8")
    local = a.out / "local" / f"round0_{a.date}_failures.csv"
    with local.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fails[0]) if fails else ["kind"])
        w.writeheader()
        w.writerows(fails)
    print(f"report: {report}\nfailures (local, do not commit): {local}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
