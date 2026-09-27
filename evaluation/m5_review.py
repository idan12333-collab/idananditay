"""M5 duplicate review (EVAL_PLAN.md): is each near-duplicate group really one moment, and which copy is best?

Why not the app's side-by-side screen: it can't jump to the sampled groups, it can't record
"these are different moments", and "no change" there is indistinguishable from "not reviewed".
This is an evaluation form, not product UI: a self-contained local HTML page (thumbnails embedded),
written to the git-ignored ``evaluation/reports/local/``. Nothing is sent anywhere and the app DB is
opened read-only.

    python -m evaluation.m5_review build --library 14      # -> reports/local/m5_review_<lib>.html
    python -m evaluation.m5_review score --library 14 --answers PATH/m5_answers.json
                                                          # -> reports/m5_<date>.md (aggregates + ids only)
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from app.core.config import Settings
from evaluation.metrics import Rate, connect_ro

REPORTS = Path(__file__).parent / "reports"
MAX_EXTRA = 6  # extra groups that hold an alternate the owner labeled wanted (the round-0 risk)


def select_groups(conn, library_id: int, sample: dict | None) -> list[dict]:
    """Near-duplicate groups to review: the seed's dup_groups stratum + groups hiding wanted alternates.

    Exact groups (identical files) are skipped: there is nothing to judge.
    """
    near = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, kind, size, best_photo_id, auto_best_photo_id FROM duplicate_groups "
        "WHERE library_id = ? AND kind = 'near'", (library_id,))}
    chosen: dict[int, str] = {}
    for it in (sample or {}).get("items", []):
        if it.get("stratum") == "dup_groups" and it.get("group_id") in near:
            chosen.setdefault(it["group_id"], "sample")
    extra = conn.execute(
        "SELECT p.duplicate_group_id AS gid, COUNT(*) AS n FROM photos p JOIN curation_labels cl "
        "ON cl.content_hash = p.content_hash WHERE p.library_id = ? AND p.status = 'ok' "
        "AND p.duplicate_group_id IS NOT NULL AND p.is_group_best = 0 AND cl.worthiness IN ('must','maybe') "
        "GROUP BY gid ORDER BY n DESC, gid", (library_id,)).fetchall()
    added = 0
    for r in extra:
        if added >= MAX_EXTRA:
            break
        if r["gid"] in near and r["gid"] not in chosen:
            chosen[r["gid"]] = "wanted_alternate"
            added += 1
    out = []
    for gid, why in chosen.items():
        g = near[gid]
        g["why"] = why
        g["members"] = [dict(m) for m in conn.execute(
            "SELECT id, content_hash, thumbnail_path, capture_time, is_group_best FROM photos "
            "WHERE duplicate_group_id = ? AND status = 'ok' ORDER BY capture_time, id", (gid,))]
        out.append(g)
    return sorted(out, key=lambda g: g["id"])


def _img(thumbs: Path, rel: str | None) -> str:
    try:
        return "data:image/jpeg;base64," + base64.b64encode((thumbs / rel).read_bytes()).decode()
    except (OSError, TypeError):
        return ""


def build_html(groups: list[dict], thumbs: Path, library_id: int) -> str:
    cards = []
    for i, g in enumerate(groups, 1):
        tiles = "".join(
            f'<label class="t{" auto" if m["id"] == g["auto_best_photo_id"] else ""}">'
            f'<input type="radio" name="best_{g["id"]}" value="{m["id"]}">'
            f'<img src="{_img(thumbs, m["thumbnail_path"])}" alt="">'
            f'<small>{html.escape((m["capture_time"] or "")[:19].replace("T", " "))}'
            f'{" · ⭐ הבחירה האוטומטית" if m["id"] == g["auto_best_photo_id"] else ""}</small></label>'
            for m in g["members"])
        cards.append(
            f'<section data-g="{g["id"]}"><h2>קבוצה {i} מתוך {len(groups)} · {g["size"]} תמונות</h2>'
            f'<p class="q">1. האם כל התמונות כאן הן אותו רגע?</p><div class="opts">'
            f'<label><input type="radio" name="same_{g["id"]}" value="same"> כן, אותו רגע</label>'
            f'<label><input type="radio" name="same_{g["id"]}" value="partial"> חלקן רגעים אחרים</label>'
            f'<label><input type="radio" name="same_{g["id"]}" value="different"> לא, רגעים שונים</label></div>'
            f'<p class="q">2. לחץ על העותק הכי טוב (⭐ = מה שהמערכת בחרה)</p><div class="row">{tiles}</div></section>')
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<title>בדיקת כפילויות</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#e3e2dc;--acc:#2f6fdb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--fg:#eceae4;--mut:#a3a19a;--card:#212120;--line:#3a3936;--acc:#7aa7ff}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:1100px;margin:auto;padding:16px}}
section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0}}
h1{{font-size:22px}} h2{{font-size:17px;margin:0 0 8px}} .q{{margin:12px 0 6px;font-weight:600}} .mut{{color:var(--mut)}}
.opts{{display:flex;gap:16px;flex-wrap:wrap}}
.row{{display:flex;gap:10px;overflow-x:auto;padding-bottom:6px}}
.t{{flex:0 0 auto;display:flex;flex-direction:column;align-items:center;cursor:pointer;border:3px solid transparent;border-radius:8px;padding:4px}}
.t input{{display:none}} .t img{{height:220px;border-radius:4px}} .t small{{color:var(--mut)}}
.t:has(input:checked){{border-color:var(--acc)}} .t.auto small{{color:var(--fg)}}
button{{font:inherit;padding:10px 18px;border-radius:8px;border:0;background:var(--acc);color:#fff;cursor:pointer}}
#status{{margin-inline-start:12px}}
</style></head><body><main>
<h1>בדיקת כפילויות · {len(groups)} קבוצות</h1>
<p class="mut">המערכת חושבת שהתמונות בכל קבוצה כמעט זהות, ומשאירה רק אחת. לכל קבוצה: ענה על שאלה 1, ולחץ על העותק הטוב ביותר.
אם הבחירה האוטומטית (⭐) טובה, לחץ עליה. זה לוקח בערך 5 דקות. הדף לא שולח שום דבר; בסוף לוחצים "שמירת התשובות".</p>
{''.join(cards)}
<p><button id="save">שמירת התשובות</button><span id="status" class="mut"></span></p>
</main><script>
const LIB={library_id};
document.getElementById('save').onclick=()=>{{
  const out=[...document.querySelectorAll('section[data-g]')].map(s=>{{const g=s.dataset.g;
    const v=n=>(s.querySelector(`input[name="${{n}}_${{g}}"]:checked`)||{{}}).value||null;
    return {{group_id:+g,same:v('same'),best:v('best')?+v('best'):null}}}});
  const missing=out.filter(a=>!a.same||!a.best).length;
  if(missing&&!confirm(`${{missing}} קבוצות לא הושלמו. לשמור בכל זאת?`))return;
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([JSON.stringify({{library_id:LIB,answers:out}},null,1)],{{type:'application/json'}}));
  a.download='m5_answers.json';a.click();
  document.getElementById('status').textContent='נשמר קובץ m5_answers.json בתיקיית ההורדות.';
}};
</script></body></html>"""


def snapshot(groups: list[dict]) -> list[dict]:
    """What score() needs, frozen at build time: group ids and photo ids change on every rescan."""
    return [{"id": g["id"], "why": g["why"], "size": g["size"], "auto_best_photo_id": g["auto_best_photo_id"],
             "member_ids": [m["id"] for m in g["members"]],
             "member_hashes": [m["content_hash"] for m in g["members"]]} for g in groups]


def groups_from_html(text: str) -> list[dict]:
    """Recover the snapshot from a page built before snapshots existed (ids + automatic keeper)."""
    out = []
    for sec in re.findall(r'<section data-g="(\d+)">(.*?)</section>', text, re.S):
        gid, body = int(sec[0]), sec[1]
        members = [int(v) for v in re.findall(r'name="best_%d" value="(\d+)"' % gid, body)]
        auto = re.search(r'class="t auto"><input type="radio" name="best_%d" value="(\d+)"' % gid, body)
        out.append({"id": gid, "why": "unknown", "size": len(members), "member_ids": members,
                    "auto_best_photo_id": int(auto.group(1)) if auto else None})
    return out


def score(groups: list[dict], answers: dict) -> dict:
    by_id = {g["id"]: g for g in groups}
    done = [a for a in answers.get("answers", []) if a.get("group_id") in by_id and a.get("same") and a.get("best")]
    same = Counter(a["same"] for a in done)
    agree = [a for a in done if a["same"] == "same"]
    return {
        "groups": len(groups), "answered": len(done), "same": dict(same),
        "merged_moments": Rate(sum(a["same"] != "same" for a in done), len(done)),
        "keeper_agreement": Rate(sum(a["best"] == by_id[a["group_id"]]["auto_best_photo_id"] for a in agree), len(agree)),
        "not_same_ids": sorted(a["group_id"] for a in done if a["same"] != "same"),
        "keeper_miss_ids": sorted(a["group_id"] for a in agree if a["best"] != by_id[a["group_id"]]["auto_best_photo_id"]),
        "by_why": dict(Counter(by_id[a["group_id"]]["why"] for a in done if a["same"] != "same")),
    }


def report(s: dict, library_id: int, today: str) -> str:
    return "\n".join([
        f"# M5 duplicate review ({today})", "",
        f"Library {library_id}. Near-duplicate groups reviewed by the owner: {s['answered']} of {s['groups']} "
        "(the seed's dup_groups stratum + groups hiding alternates the owner labeled wanted). Exact-copy groups are excluded.", "",
        "| Metric | Value |", "|---|---|",
        f"| Grouping merged different moments (partial/different) | {s['merged_moments'].fmt()} |",
        f"| M5 keeper agreement (auto keeper == owner's pick, same-moment groups) | {s['keeper_agreement'].fmt()} |", "",
        f"Answers: {s['same']}. Groups with merged moments: {s['not_same_ids']} (by selection reason: {s['by_why']}). "
        f"Keeper misses: {s['keeper_miss_ids']}.", ""])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("build", "score"))
    ap.add_argument("--library", type=int, required=True)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--sample", type=Path, help="seed sample JSON (default: <data_dir>/seed/seed_sample_lib<N>.json)")
    ap.add_argument("--answers", type=Path)
    ap.add_argument("--out", type=Path, default=REPORTS)
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args(argv)
    settings = Settings()
    sample_path = a.sample or settings.data_dir / "seed" / f"seed_sample_lib{a.library}.json"
    local = a.out / "local"
    page, snap = local / f"m5_review_{a.library}.html", local / f"m5_groups_{a.library}.json"
    if a.cmd == "build":
        sample = json.loads(sample_path.read_text(encoding="utf-8")) if sample_path.exists() else None
        conn = connect_ro(a.db or settings.db_path)
        try:
            groups = select_groups(conn, a.library, sample)
        finally:
            conn.close()
        local.mkdir(parents=True, exist_ok=True)
        page.write_text(build_html(groups, settings.thumbnails_dir, a.library), encoding="utf-8")
        snap.write_text(json.dumps(snapshot(groups)), encoding="utf-8")
        print(f"{len(groups)} groups -> {page} (local only, do not commit)")
    else:
        if not a.answers:
            ap.error("score needs --answers")
        # Score against the groups as the owner saw them, never the live DB (a rescan renumbers groups).
        if snap.exists():
            groups = json.loads(snap.read_text(encoding="utf-8"))
        elif page.exists():
            groups = groups_from_html(page.read_text(encoding="utf-8"))
        else:
            ap.error(f"no snapshot or page for library {a.library} in {local}")
        s = score(groups, json.loads(a.answers.read_text(encoding="utf-8")))
        path = a.out / f"m5_{a.date}.md"
        path.write_text(report(s, a.library, a.date), encoding="utf-8")
        print(f"report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
