"""Retrieval evaluation (EVAL_PLAN.md "Retrieval rounds"): does a text query find the photos the owner wants?

Method: queries_template_researched.md. Three local owner pages + a scorer. Nothing leaves the PC:
pages are plain local HTML files (thumbnails loaded from the app's thumbnail folder), answers are
downloaded as JSON and kept under the git-ignored ``evaluation/reports/local/``. The app DB is read-only.
All ground truth is keyed by content_hash (library/photo IDs are renumbered when a library is re-created).

    python -m evaluation.retrieval_eval embed    --library 15            # cache image embeddings (both models)
    python -m evaluation.retrieval_eval choose   --library 15            # page 1: which queries exist in my library?
    python -m evaluation.retrieval_eval mustfind --library 15 --choice C # page 2: MUST_FIND by browsing dates (no model)
    python -m evaluation.retrieval_eval pool     --library 15 --choice C [--grades G ...]  # page 3: pooled 0–3 grading
    python -m evaluation.retrieval_eval score    --library 15 --choice C --mustfind M --grades G [G ...]

Models come from evaluation/poc_7a_semantic_search.py (the 7a POC), imported read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

from app.core.config import Settings
from evaluation.metrics import connect_ro

HERE = Path(__file__).parent
CANDIDATES = HERE / "retrieval_candidates.json"
LOCAL = HERE / "reports" / "local"
FEASIBILITY_MODEL = "openclip_xlmr_b32"  # multilingual; used ONLY to show whether a query is feasible
POOL_K = 20
MUSTFIND_DEPTH = 30   # per model × language; 4 rankings overlap heavily -> ~60–100 photos per query
MUSTFIND_RANDOM = 20  # random control photos per query
HELD_OUT_SHARE = 0.25


# ----------------------------------------------------------------------------- data
def library_photos(conn, library_id: int) -> list[dict]:
    """One row per distinct content (exact copies collapse), with what the pages and scorer need."""
    rows = conn.execute(
        "SELECT MIN(id) AS id, content_hash, thumbnail_path, MIN(capture_time) AS capture_time, "
        "MAX(duplicate_group_id) AS dup_group FROM photos WHERE library_id = ? AND status = 'ok' "
        "AND content_hash IS NOT NULL AND thumbnail_path IS NOT NULL GROUP BY content_hash "
        "ORDER BY capture_time IS NULL, capture_time, id", (library_id,)).fetchall()
    return [dict(r) for r in rows]


def emb_path(model: str, library_id: int) -> Path:
    return LOCAL / f"emb_{model}_lib{library_id}.npz"


def load_embeddings(model: str, library_id: int) -> tuple[list[str], np.ndarray]:
    z = np.load(emb_path(model, library_id), allow_pickle=False)
    return [str(h) for h in z["hashes"]], z["vecs"]


def rank(query_vec: np.ndarray, hashes: list[str], vecs: np.ndarray) -> list[str]:
    order = np.argsort(-(vecs @ query_vec), kind="stable")
    return [hashes[i] for i in order]


def _qhash(query_id: str) -> int:
    return int(hashlib.sha256(query_id.encode()).hexdigest()[:8], 16)


def held_out_ids(query_ids: list[str]) -> set[str]:
    """Exactly ceil(25%) of the chosen queries, the ones with the lowest id hash: deterministic and
    independent of any result. (A per-query hash test is too noisy for ~12 queries: it gave 9/12.)"""
    n = math.ceil(len(query_ids) * HELD_OUT_SHARE)
    return set(sorted(query_ids, key=_qhash)[:n])


def chosen_queries(choice: dict) -> list[dict]:
    cands = {q["id"]: q for q in json.loads(CANDIDATES.read_text(encoding="utf-8"))["queries"]}
    out = []
    for a in choice.get("queries", []):
        if a.get("feasible") in ("yes", "few"):
            q = dict(cands.get(a["id"], {"id": a["id"], "he": a.get("he", ""), "en": a.get("en", ""), "hn": ""}))
            out.append(q)
    for i, x in enumerate(choice.get("extra", []), 1):  # the owner's own queries (may name people/places)
        qid = f"x{i}"
        out.append({"id": qid, "he": x.get("he", ""), "en": x.get("en", ""), "hn": x.get("hn", "")})
    held = held_out_ids([q["id"] for q in out])
    return [{**q, "held_out": q["id"] in held} for q in out]


# ----------------------------------------------------------------------------- metrics (pure)
def dcg(grades: list[int]) -> float:
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades))


def query_metrics(ranking: list[str], must: set[str], grades: dict[str, object], dup_group: dict[str, int | None],
                  other_lang_ranking: list[str] | None = None) -> dict:
    """R1–R6 for one query. Grades: 0–3 or 'hn' (a hard negative, counts as 0). A MUST_FIND photo
    without a grade counts as 3. Unjudged results count as 0 and are reported as judged coverage."""
    def g(h):
        v = grades.get(h, 3 if h in must else None)
        return 0 if v in (None, "hn") else int(v)

    top10, top20 = ranking[:10], ranking[:20]
    ideal = sorted([g(h) for h in set(grades) | must], reverse=True)[:20]
    seen_groups, dups = set(), 0
    for h in top20:
        grp = dup_group.get(h)
        if grp is not None:
            dups += grp in seen_groups
            seen_groups.add(grp)
    out = {
        "must_n": len(must),
        "must_recall@20": (len(must & set(top20)) / len(must)) if must else None,
        "must_recall@50": (len(must & set(ranking[:50])) / len(must)) if must else None,
        "p@10": sum(g(h) >= 2 for h in top10) / 10,
        "ndcg@20": (dcg([g(h) for h in top20]) / dcg(ideal)) if ideal and dcg(ideal) > 0 else None,
        "hn@10": sum(grades.get(h) == "hn" for h in top10) / 10,
        "dup@20": dups / len(top20) if top20 else 0.0,
        "judged@10": sum(h in grades or h in must for h in top10) / 10,
    }
    if other_lang_ranking is not None:
        a, b = set(top20), set(other_lang_ranking[:20])
        out["he_en_overlap@20"] = len(a & b) / len(a | b) if a | b else None
    return out


def mean(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


# ----------------------------------------------------------------------------- pages
CSS = """:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#e3e2dc;--acc:#2f6fdb;--ok:#1f8a4c;--bad:#c2410c}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#eceae4;--mut:#a3a19a;--card:#212120;--line:#3a3936;--acc:#7aa7ff;--ok:#4cc27f;--bad:#fb8c5a}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:1200px;margin:auto;padding:16px}h1{font-size:22px;margin:0 0 6px}h2{font-size:17px;margin:0 0 8px}
.mut{color:var(--mut)}section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:14px 0}
.row{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px}.row img,.grid img{height:130px;border-radius:4px;display:block}
.grid{display:flex;flex-wrap:wrap;gap:6px}.opts{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
.pick{border:3px solid transparent;border-radius:6px;cursor:pointer}.pick.on{border-color:var(--ok)}
button{font:inherit;padding:8px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.primary{background:var(--acc);color:#fff;border:0}button.on{outline:3px solid var(--acc)}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);z-index:2;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
select,textarea{font:inherit;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px}
.big{height:min(60vh,520px)!important;max-width:100%;object-fit:contain}"""

SAVE_JS = """function saveJson(name,obj){const a=document.createElement('a');
a.href=URL.createObjectURL(new Blob([JSON.stringify(obj,null,1)],{type:'application/json'}));a.download=name;a.click();
document.getElementById('status').textContent='נשמר '+name+' (תיקיית ההורדות). שלח לי הודעה שסיימת.';}"""


def page(title: str, body: str, data: dict, script: str) -> str:
    return (f'<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><title>{title}</title>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head>'
            f'<body><main>{body}<p><span id="status" class="mut"></span></p></main>'
            f'<script>const DATA={json.dumps(data, ensure_ascii=False)};{SAVE_JS}{script}</script></body></html>')


def thumb_uri(thumbs: Path, rel: str) -> str:
    return (thumbs / rel).as_uri()


def build_choose(library_id: int, cands: list[dict], tops: dict[str, list[str]], thumb: dict[str, str]) -> str:
    data = {"lib": library_id, "q": [{**c, "top": [thumb[h] for h in tops[c["id"]]]} for c in cands]}
    body = ("<h1>שלב 1: אילו חיפושים מתאימים לספרייה שלך?</h1><p class='mut'>לכל חיפוש מוצגות 8 התמונות הראשונות "
            "שמודל אחד מצא, רק כדי להזכיר לך מה יש. השאלה היא לא אם המודל צדק, אלא <b>האם יש בספרייה שלך תמונות כאלה</b>. "
            "בסוף אפשר להוסיף חיפושים משלך (טיול, אירוע, מקום). ~10 דקות.</p><div id='list'></div>"
            "<section><h2>חיפושים משלך (לא חובה)</h2><p class='mut'>שורה לכל חיפוש: עברית | אנגלית (לא חובה). "
            "למשל: טיול לאילת | trip to Eilat</p><textarea id='extra' rows='5' style='width:100%'></textarea></section>"
            "<button class='primary' id='save'>שמירת הבחירה</button>")
    script = """const L=document.getElementById('list');DATA.q.forEach((q,i)=>{L.insertAdjacentHTML('beforeend',
`<section><h2>${i+1}. ${q.he} <span class="mut">· ${q.en}</span></h2><div class="row">${q.top.map(u=>`<img loading="lazy" src="${u}">`).join('')}</div>
<div class="opts"><label><input type="radio" name="f_${q.id}" value="yes"> יש לי כאלה</label>
<label><input type="radio" name="f_${q.id}" value="few"> יש מעט (1–3)</label>
<label><input type="radio" name="f_${q.id}" value="no"> אין לי כאלה</label></div></section>`)});
document.getElementById('save').onclick=()=>{const qs=DATA.q.map(q=>({id:q.id,feasible:(document.querySelector(`input[name="f_${q.id}"]:checked`)||{}).value||null}));
const miss=qs.filter(q=>!q.feasible).length;if(miss&&!confirm(miss+' חיפושים בלי תשובה. לשמור בכל זאת?'))return;
const extra=document.getElementById('extra').value.split('\\n').map(s=>s.trim()).filter(Boolean).map(s=>{const [he,en]=s.split('|').map(x=>(x||'').trim());return {he,en}});
saveJson('r1_choice.json',{library_id:DATA.lib,queries:qs,extra});};"""
    return page("בחירת חיפושים", body, data, script)


def mustfind_candidates(queries: list[dict], rankings: dict[tuple[str, str, str], list[str]], all_hashes: list[str],
                        depth: int = MUSTFIND_DEPTH, n_random: int = MUSTFIND_RANDOM, seed: int = 20260927) -> dict[str, list[str]]:
    """Per query: the union of the top `depth` of every model × language, plus `n_random` random photos as a
    control (TREC-style pooling). Shown by date, unranked, so the owner can't tell who proposed what.
    Caveat (reported): MUST_FIND recall is then relative to this pool, not to the whole library."""
    rnd = random.Random(seed)
    out = {}
    for q in queries:
        pool = set()
        for (model, lang, qid), r in rankings.items():
            if qid == q["id"]:
                pool.update(r[:depth])
        rest = sorted(set(all_hashes) - pool)
        pool.update(rnd.sample(rest, min(n_random, len(rest))))
        out[q["id"]] = sorted(pool)
    return out


def build_mustfind(library_id: int, queries: list[dict], photos: list[dict], thumbs: Path,
                   candidates: dict[str, list[str]] | None = None) -> str:
    wanted = set().union(*candidates.values()) if candidates else None
    months: dict[str, list] = defaultdict(list)
    for p in photos:
        if wanted is None or p["content_hash"] in wanted:
            months[(p["capture_time"] or "ללא תאריך")[:7]].append([p["content_hash"], thumb_uri(thumbs, p["thumbnail_path"])])
    data = {"lib": library_id, "q": [{"id": q["id"], "he": q["he"]} for q in queries], "months": list(months.items()),
            "cand": candidates}
    body = ("<h1>שלב 2: תמונות שחייבים למצוא</h1><p class='mut'>בוחרים חיפוש למעלה, ואז לוחצים על 3–10 תמונות "
            "שהמערכת <b>חייבת</b> למצוא בחיפוש הזה. לכל חיפוש מוצגות כ-100 תמונות מועמדות בלבד, מסודרות לפי תאריך "
            "(בלי דירוג, וחלקן אקראיות). לחיצה נוספת מבטלת. אם אין בכלל תמונה מתאימה, עוברים לחיפוש הבא.</p>"
            "<div class='bar'><select id='q'></select><span id='count' class='mut'></span>"
            "<button class='primary' id='save'>שמירה</button></div><div id='months'></div>")
    script = """const sel=document.getElementById('q'),picks={};DATA.q.forEach(q=>{picks[q.id]=new Set();sel.insertAdjacentHTML('beforeend',`<option value="${q.id}">${q.he}</option>`)});
const M=document.getElementById('months');DATA.months.forEach(([m,items])=>{M.insertAdjacentHTML('beforeend',`<section><h2>${m} <span class="mut">(${items.length})</span></h2><div class="grid">${items.map(([h,u])=>`<img loading="lazy" class="pick" data-h="${h}" src="${u}">`).join('')}</div></section>`)});
function paint(){const s=picks[sel.value],c=DATA.cand?new Set(DATA.cand[sel.value]):null;
document.querySelectorAll('.pick').forEach(e=>{e.classList.toggle('on',s.has(e.dataset.h));e.hidden=c?!c.has(e.dataset.h):false;});
document.querySelectorAll('#months section').forEach(sec=>sec.hidden=![...sec.querySelectorAll('.pick')].some(e=>!e.hidden));window.scrollTo(0,0);
document.getElementById('count').textContent='נבחרו '+s.size+' לחיפוש הזה · '+DATA.q.filter(q=>picks[q.id].size).length+'/'+DATA.q.length+' חיפושים עם בחירה';}
M.onclick=e=>{const h=e.target.dataset&&e.target.dataset.h;if(!h)return;const s=picks[sel.value];s.has(h)?s.delete(h):s.add(h);e.target.classList.toggle('on',s.has(h));
document.getElementById('count').textContent='נבחרו '+s.size+' לחיפוש הזה · '+DATA.q.filter(q=>picks[q.id].size).length+'/'+DATA.q.length+' חיפושים עם בחירה';};sel.onchange=paint;paint();
document.getElementById('save').onclick=()=>saveJson('r1_mustfind.json',{library_id:DATA.lib,pooled:!!DATA.cand,must_find:Object.fromEntries(Object.entries(picks).map(([k,v])=>[k,[...v]]))});"""
    return page("חייבים למצוא", body, data, script)


def build_pool(library_id: int, items: list[dict], thumb: dict[str, str]) -> str:
    """Grid grading per query: every pooled photo of the query on one screen; a click cycles
    none → ✓ relevant (2) → ★ excellent (3) → X confusable (hn) → none. Unmarked on save = 0.
    (Grade 1 "partial" was dropped: the one-by-one 0–3 flow was too slow for ~500 photos.)"""
    qs: dict[str, dict] = {}
    for it in items:
        qs.setdefault(it["q"], {"id": it["q"], "he": it["he"], "hn": it["hn"], "items": []})["items"].append([it["h"], thumb[it["h"]]])
    data = {"lib": library_id, "q": list(qs.values())}
    body = ("<h1>שלב 3: סימון תוצאות</h1><p class='mut'>לכל חיפוש מוצגות כל התמונות שהמודלים החזירו, מעורבבות. "
            "לחיצה על תמונה מחליפה סימון: <b>✓ מתאימה</b> → <b>★ מצוינת</b> → <b>X מבלבלת</b> (הדבר הדומה שאסור שיציף) → בלי סימון. "
            "תמונה בלי סימון = לא מתאימה. התמונות שכבר בחרת כ'חייבים למצוא' לא מופיעות שוב.</p>"
            "<div class='bar'><select id='q'></select><span id='count' class='mut'></span><button id='nextq'>לחיפוש הבא ←</button>"
            "<button class='primary' id='save'>שמירה</button></div><p id='hn' class='mut'></p><div id='grid' class='grid'></div>")
    script = """const CY=[null,2,3,'hn'],LBL={2:'✓',3:'★',hn:'X'},G={};const sel=document.getElementById('q'),grid=document.getElementById('grid'),seen=new Set();
DATA.q.forEach(q=>{G[q.id]={};sel.insertAdjacentHTML('beforeend',`<option value="${q.id}">${q.he} (${q.items.length})</option>`)});
function cur(){return DATA.q.find(q=>q.id===sel.value)}
function render(){const q=cur();seen.add(q.id);document.getElementById('hn').textContent=q.hn?('מבלבל בחיפוש הזה: '+q.hn):'';
grid.innerHTML=q.items.map(([h,u])=>`<div class="cell" data-h="${h}" style="position:relative;cursor:pointer"><img loading="lazy" src="${u}"><b class="tag" style="position:absolute;top:4px;inset-inline-start:6px;font-size:22px;text-shadow:0 0 4px #000;color:#fff"></b></div>`).join('');paint();window.scrollTo(0,0);}
function paint(){const g=G[sel.value];grid.querySelectorAll('.cell').forEach(c=>{const v=g[c.dataset.h];c.querySelector('.tag').textContent=v==null?'':LBL[v];
c.querySelector('img').style.outline=v==null?'none':('4px solid '+(v==='hn'?'var(--bad)':'var(--ok)'));});
const n=Object.keys(G[sel.value]).length;document.getElementById('count').textContent='סומנו '+n+' · עברת על '+seen.size+'/'+DATA.q.length+' חיפושים';}
grid.onclick=e=>{const c=e.target.closest('.cell');if(!c)return;const g=G[sel.value],h=c.dataset.h,v=CY[(CY.indexOf(g[h]??null)+1)%CY.length];if(v==null)delete g[h];else g[h]=v;paint();};
sel.onchange=render;document.getElementById('nextq').onclick=()=>{if(sel.selectedIndex<DATA.q.length-1){sel.selectedIndex++;render();}};render();
document.getElementById('save').onclick=()=>{const miss=DATA.q.filter(q=>!seen.has(q.id)).length;if(miss&&!confirm(miss+' חיפושים שעוד לא פתחת. לשמור בכל זאת?'))return;
const out={};DATA.q.forEach(q=>{if(!seen.has(q.id))return;out[q.id]={};q.items.forEach(([h])=>{out[q.id][h]=G[q.id][h]??0})});saveJson('r1_grades.json',{library_id:DATA.lib,grades:out});};"""
    return page("סימון תוצאות", body, data, script)


def pool_items(queries: list[dict], rankings: dict[tuple[str, str, str], list[str]], graded: dict[str, dict],
               must: dict[str, set[str]] | None = None, depth: int = POOL_K, seed: int = 20260927) -> list[dict]:
    """Union of the top `depth` of every model × language per query, minus already-graded and MUST_FIND
    photos (those count as grade 3). Grouped by query (faster to grade), shuffled within each query so
    the model order stays hidden."""
    rnd, items = random.Random(seed), []
    for q in queries:
        pooled = set()
        for (model, lang, qid), r in rankings.items():
            if qid == q["id"]:
                pooled.update(r[:depth])
        todo = sorted(pooled - set(graded.get(q["id"], {})) - (must or {}).get(q["id"], set()))
        rnd.shuffle(todo)
        items += [{"q": q["id"], "he": q["he"], "hn": q.get("hn", ""), "h": h} for h in todo]
    return items


def merge_grades(paths: list[Path]) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(dict)
    for p in paths:
        for q, gs in json.loads(p.read_text(encoding="utf-8")).get("grades", {}).items():
            out[q].update(gs)
    return dict(out)


# ----------------------------------------------------------------------------- report
def build_report(library_id: int, queries: list[dict], results: dict, today: str) -> str:
    cols = ["must_recall@20", "must_recall@50", "p@10", "ndcg@20", "hn@10", "dup@20", "he_en_overlap@20", "judged@10"]
    fmt = lambda v: "n/a" if v is None else f"{v:.2f}"  # noqa: E731
    L = [f"# Retrieval round 1 ({today})", "",
         f"Library {library_id}. {len(queries)} owner-chosen queries ({sum(q['held_out'] for q in queries)} held out). "
         "MUST_FIND picked by date browsing (no model); grades pooled over all models × languages, model hidden.", "",
         "## Mean over queries", "", "| model | lang | split | " + " | ".join(cols) + " |", "|---" * (len(cols) + 3) + "|"]
    for (model, lang), per_q in sorted(results.items()):
        for split, keep in (("all", lambda q: True), ("tuning", lambda q: not q["held_out"]), ("held-out", lambda q: q["held_out"])):
            ms = [per_q[q["id"]] for q in queries if keep(q) and q["id"] in per_q]
            if ms:
                L.append(f"| {model} | {lang} | {split} | " + " | ".join(fmt(mean([m.get(c) for m in ms])) for c in cols) + " |")
    L += ["", "## Per query (tuning + held-out)", "", "| query | held-out | model | lang | must n | R@20 | P@10 | nDCG@20 | HN@10 | dup@20 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for q in queries:
        label = q["id"] if q["id"].startswith("x") else f"{q['id']} ({q['en']})"  # owner's own queries: id only
        for (model, lang), per_q in sorted(results.items()):
            m = per_q.get(q["id"])
            if m:
                L.append(f"| {label} | {int(q['held_out'])} | {model} | {lang} | {m['must_n']} | {fmt(m['must_recall@20'])} | "
                         f"{fmt(m['p@10'])} | {fmt(m['ndcg@20'])} | {fmt(m['hn@10'])} | {fmt(m['dup@20'])} |")
    L += ["", "Caveats: one library (2025–2026, ~1.1k photos), CPU, thumbnails as model input; small n per query. "
          "`judged@10` < 1.00 means unjudged results were counted as irrelevant (grade them with `pool`)."]
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("embed", "choose", "mustfind", "pool", "score"))
    ap.add_argument("--library", type=int, required=True)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--models", nargs="+", default=["siglip2_base", "openclip_xlmr_b32"])
    ap.add_argument("--choice", type=Path)
    ap.add_argument("--mustfind", type=Path)
    ap.add_argument("--grades", type=Path, nargs="*", default=[])
    ap.add_argument("--depth", type=int, default=POOL_K, help="pool depth per model × language (pool)")
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args(argv)
    settings = Settings()
    conn = connect_ro(a.db or settings.db_path)
    try:
        photos = library_photos(conn, a.library)
    finally:
        conn.close()
    thumbs = settings.thumbnails_dir
    thumb = {p["content_hash"]: thumb_uri(thumbs, p["thumbnail_path"]) for p in photos}
    LOCAL.mkdir(parents=True, exist_ok=True)
    out_html = lambda name: LOCAL / f"{name}_lib{a.library}.html"  # noqa: E731

    from evaluation.poc_7a_semantic_search import build_model  # heavy imports only when a model is needed

    if a.cmd == "embed":
        from PIL import Image
        for name in a.models:
            model, hashes, vecs = build_model(name), [], []
            for i in range(0, len(photos), 32):
                batch = photos[i:i + 32]
                imgs = [Image.open(thumbs / p["thumbnail_path"]).convert("RGB") for p in batch]
                vecs.append(model.embed_images(imgs))
                hashes += [p["content_hash"] for p in batch]
            np.savez(emb_path(name, a.library), hashes=np.array(hashes), vecs=np.concatenate(vecs))
            print(f"{name}: {len(hashes)} photos -> {emb_path(name, a.library)}")
        return 0

    if a.cmd == "choose":
        cands = json.loads(CANDIDATES.read_text(encoding="utf-8"))["queries"]
        model = build_model(FEASIBILITY_MODEL)
        hashes, vecs = load_embeddings(FEASIBILITY_MODEL, a.library)
        qv = model.embed_text([c["he"] for c in cands])
        tops = {c["id"]: rank(qv[i], hashes, vecs)[:8] for i, c in enumerate(cands)}
        out_html("r1_choose").write_text(build_choose(a.library, cands, tops, thumb), encoding="utf-8")
        print(f"{len(cands)} candidates -> {out_html('r1_choose')}")
        return 0

    queries = chosen_queries(json.loads(a.choice.read_text(encoding="utf-8")))
    rankings: dict[tuple[str, str, str], list[str]] = {}
    for name in a.models:
        model = build_model(name)
        hashes, vecs = load_embeddings(name, a.library)
        for lang in ("he", "en"):
            texts = [(q["id"], q[lang]) for q in queries if q.get(lang)]
            if texts:
                qv = model.embed_text([t for _, t in texts])
                for i, (qid, _) in enumerate(texts):
                    rankings[(name, lang, qid)] = rank(qv[i], hashes, vecs)
    grades = merge_grades(a.grades)

    if a.cmd == "mustfind":  # pooled candidates, shown unranked by date (owner found 1,080 per query unworkable)
        cands = mustfind_candidates(queries, rankings, [p["content_hash"] for p in photos])
        out_html("r1_mustfind").write_text(build_mustfind(a.library, queries, photos, thumbs, cands), encoding="utf-8")
        sizes = sorted(len(v) for v in cands.values())
        print(f"{len(queries)} queries, candidates per query {sizes[0]}–{sizes[-1]} -> {out_html('r1_mustfind')}")
        return 0

    if a.cmd == "pool":
        must = ({q: set(v) for q, v in json.loads(a.mustfind.read_text(encoding="utf-8")).get("must_find", {}).items()}
                if a.mustfind else {})
        items = pool_items(queries, rankings, grades, must, a.depth)
        out_html("r1_pool").write_text(build_pool(a.library, items, thumb), encoding="utf-8")
        print(f"{len(items)} new (query, photo) pairs to grade -> {out_html('r1_pool')}")
        return 0

    must = {q: set(v) for q, v in json.loads(a.mustfind.read_text(encoding="utf-8")).get("must_find", {}).items()}
    dup_group = {p["content_hash"]: p["dup_group"] for p in photos}
    results: dict[tuple[str, str], dict] = defaultdict(dict)
    for (name, lang, qid), r in rankings.items():
        other = rankings.get((name, "en" if lang == "he" else "he", qid))
        results[(name, lang)][qid] = query_metrics(r, must.get(qid, set()), grades.get(qid, {}), dup_group, other)
    report = HERE / "reports" / f"r1_{a.date}.md"
    report.write_text(build_report(a.library, queries, dict(results), a.date), encoding="utf-8")
    print(f"report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
