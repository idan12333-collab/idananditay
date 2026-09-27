"""7a semantic-search POC: does an image-text embedding model beat the M1 classical filter on junk
retention (M4), without losing any "must" or "special" photo (M1/M2, structural conservatism, ADR-021)?

Compares two candidate models (MODEL_REGISTRY.md, licenses verified 2026-09-27):
- SigLIP 2 base (google/siglip2-base-patch16-256, Apache-2.0)
- OpenCLIP xlm-roberta-base-ViT-B-32 / laion5b_s13b_b90k (MIT, POC_ONLY: LAION-5B provenance)

Read-only: the DB is opened with mode=ro, exactly like evaluation/metrics.py. Never writes to
photos/curation_labels. Does not touch app/** or any schema.

Primary measurement (works even before evaluation/queries_template.md has real owner queries):
a fixed, small set of multilingual "keep" vs "junk" text prompts gives each labeled photo a semantic
relevance score. The safe threshold is the lowest score among "must"/"special" photos (never lose one
of those); junk-removed at that threshold is directly comparable to the round-0 M4 junk-retention
baseline (evaluation/reports/round0_2026-09-27.md: ~51-52%).

Secondary, qualitative only (never used as the pass/fail number): top-K results for the few
illustrative example queries already sitting in queries_template.md. Written only to the git-ignored
local/ report, since it names real files, exactly like metrics.py's failures CSV.

Usage:
    python -m evaluation.poc_7a_semantic_search --library 15 [--db PATH] [--limit N] [--out evaluation/reports]
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image

from app.core.config import Settings
from evaluation.metrics import Rate, connect_ro

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

# ----------------------------------------------------------------------------- prompts (fixed, not tuned per-photo)
KEEP_PROMPTS = [
    "a meaningful photo of a person, family, or pet, worth keeping in a photo album",
    "a photo of a special moment, celebration, or trip",
    "תמונה משמעותית של אדם, משפחה או חיית מחמד, ששווה לשמור באלבום",
    "תמונה של רגע מיוחד, חגיגה או טיול",
]
JUNK_PROMPTS = [
    "a screenshot of a phone or computer screen",
    "a blurry, dark, overexposed, or accidental photo of nothing in particular",
    "a boring photo of a random object, document, or receipt, not worth keeping",
    "צילום מסך של טלפון או מחשב",
    "תמונה מטושטשת, כהה, שרופה או תמונה מקרית של כלום מיוחד",
]

QUALITATIVE_QUERIES = [
    ("dog_on_couch", "a dog on the couch", "כלב על הספה"),
    ("japan", "Japan, Japanese street or landscape", "יפן"),
]

MODELS = ("siglip2_base", "openclip_xlmr_b32")


# ----------------------------------------------------------------------------- data
@dataclass
class LabeledPhoto:
    id: int
    source_path: str
    worthiness: str
    special: bool
    held_out: bool
    stratum: str | None


def load_labeled_photos(conn: sqlite3.Connection, library_id: int, limit: int | None) -> list[LabeledPhoto]:
    q = (
        "SELECT p.id, p.source_path, cl.worthiness, cl.special, cl.held_out, cl.stratum "
        "FROM curation_labels cl JOIN photos p ON p.content_hash = cl.content_hash "
        "WHERE p.library_id = ? AND p.status = 'ok' AND p.id = ("
        "  SELECT MIN(q.id) FROM photos q WHERE q.library_id = p.library_id "
        "  AND q.status = 'ok' AND q.content_hash = p.content_hash)"
    )
    rows = conn.execute(q, (library_id,)).fetchall()
    out = [
        LabeledPhoto(r["id"], r["source_path"], r["worthiness"], bool(r["special"]), bool(r["held_out"]), r["stratum"])
        for r in rows
    ]
    return out[:limit] if limit else out


def load_images(photos: list[LabeledPhoto]) -> tuple[list[LabeledPhoto], list[Image.Image]]:
    """Best-effort decode; unreadable files are dropped (reported), never crash the run."""
    ok_photos, images, failed = [], [], []
    for p in photos:
        try:
            img = Image.open(p.source_path).convert("RGB")
            img.load()
        except Exception as exc:  # noqa: BLE001 - a single bad file must not abort the POC run
            failed.append((p.id, type(exc).__name__))
            continue
        ok_photos.append(p)
        images.append(img)
    if failed:
        print(f"  {len(failed)} photo(s) failed to decode and were skipped: {failed}")
    return ok_photos, images


# ----------------------------------------------------------------------------- models
class EmbeddingModel:
    name: str

    def embed_images(self, images: list[Image.Image], batch_size: int = 16) -> np.ndarray: ...

    def embed_text(self, texts: list[str]) -> np.ndarray: ...


class SigLIP2Base(EmbeddingModel):
    name = "siglip2_base"
    model_id = "google/siglip2-base-patch16-256"

    def __init__(self) -> None:
        import torch
        from transformers import AutoModel, AutoProcessor

        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(self.model_id)
        self.model = AutoModel.from_pretrained(self.model_id)
        self.model.eval()

    def embed_images(self, images: list[Image.Image], batch_size: int = 16) -> np.ndarray:
        out = []
        for i in range(0, len(images), batch_size):
            batch = images[i : i + batch_size]
            inputs = self.processor(images=batch, return_tensors="pt")
            with self.torch.no_grad():
                feats = _pooled(self.model.get_image_features(**inputs))
            out.append(_normalize(feats.numpy()))
        return np.concatenate(out, axis=0)

    def embed_text(self, texts: list[str]) -> np.ndarray:
        inputs = self.processor(text=texts, padding="max_length", return_tensors="pt")
        with self.torch.no_grad():
            feats = _pooled(self.model.get_text_features(**inputs))
        return _normalize(feats.numpy())


class OpenClipXlmRobertaB32(EmbeddingModel):
    name = "openclip_xlmr_b32"
    model_arch = "xlm-roberta-base-ViT-B-32"
    pretrained = "laion5b_s13b_b90k"

    def __init__(self) -> None:
        import open_clip
        import torch

        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            self.model_arch, pretrained=self.pretrained
        )
        self.tokenizer = open_clip.get_tokenizer(self.model_arch)
        self.model.eval()

    def embed_images(self, images: list[Image.Image], batch_size: int = 16) -> np.ndarray:
        out = []
        for i in range(0, len(images), batch_size):
            batch = images[i : i + batch_size]
            tensor = self.torch.stack([self.preprocess(img) for img in batch])
            with self.torch.no_grad():
                feats = self.model.encode_image(tensor)
            out.append(_normalize(feats.numpy()))
        return np.concatenate(out, axis=0)

    def embed_text(self, texts: list[str]) -> np.ndarray:
        tokens = self.tokenizer(texts)
        with self.torch.no_grad():
            feats = self.model.encode_text(tokens)
        return _normalize(feats.numpy())


def _normalize(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _pooled(feats):
    """transformers 5.x's SigLIP2 get_image_features/get_text_features return the raw encoder
    output (BaseModelOutputWithPooling), not a plain tensor; pooler_output is the pooled embedding."""
    return feats.pooler_output if hasattr(feats, "pooler_output") else feats


def build_model(name: str) -> EmbeddingModel:
    if name == "siglip2_base":
        return SigLIP2Base()
    if name == "openclip_xlmr_b32":
        return OpenClipXlmRobertaB32()
    raise ValueError(name)


# ----------------------------------------------------------------------------- measurement
def relevance_scores(model: EmbeddingModel, image_embeds: np.ndarray) -> np.ndarray:
    keep = model.embed_text(KEEP_PROMPTS)
    junk = model.embed_text(JUNK_PROMPTS)
    keep_sim = (image_embeds @ keep.T).mean(axis=1)
    junk_sim = (image_embeds @ junk.T).mean(axis=1)
    return keep_sim - junk_sim


def safe_threshold_junk_removal(photos: list[LabeledPhoto], scores: np.ndarray, view: str) -> dict:
    """The lowest score among must/special photos is the safe cutoff (never lose one of those,
    same structural-conservatism spirit as ADR-021). Junk-removed at that cutoff is comparable to M4.
    """
    must_special_idx = [i for i, p in enumerate(photos) if p.worthiness == "must" or (p.special and p.worthiness != "no")]
    no_idx = [i for i, p in enumerate(photos) if p.worthiness == "no"]
    if not must_special_idx or not no_idx:
        return {"view": view, "n_must_special": len(must_special_idx), "n_no": len(no_idx), "threshold": None,
                "junk_removed": None, "junk_retained": None}
    threshold = float(scores[must_special_idx].min())
    removed = int((scores[no_idx] < threshold).sum())
    retained = Rate(len(no_idx) - removed, len(no_idx))
    return {
        "view": view,
        "n_must_special": len(must_special_idx),
        "n_no": len(no_idx),
        "threshold": threshold,
        "junk_removed": Rate(removed, len(no_idx)).fmt(),
        "junk_retained": retained.fmt(),
    }


def mean_by_worthiness(photos: list[LabeledPhoto], scores: np.ndarray) -> dict[str, float]:
    out = {}
    for w in ("must", "maybe", "no"):
        idx = [i for i, p in enumerate(photos) if p.worthiness == w]
        if idx:
            out[w] = float(scores[idx].mean())
    return out


def qualitative_topk(model: EmbeddingModel, photos: list[LabeledPhoto], image_embeds: np.ndarray, k: int = 5) -> list[dict]:
    out = []
    for slug, en, he in QUALITATIVE_QUERIES:
        for lang, text in (("en", en), ("he", he)):
            q = model.embed_text([text])[0]
            sims = image_embeds @ q
            top = np.argsort(-sims)[:k]
            out.append({
                "query": f"{slug}/{lang}", "text": text,
                "results": [{"file": Path(photos[i].source_path).name, "score": round(float(sims[i]), 3),
                             "worthiness": photos[i].worthiness} for i in top],
            })
    return out


# ----------------------------------------------------------------------------- report
def build_report(library_id: int, n: int, results: dict[str, dict], today: str) -> str:
    L = [
        f"# 7a semantic-search POC ({today})",
        "",
        f"Library {library_id}. {n} labeled photos scored (curation_labels, same dedup rule as evaluation/metrics.py). "
        "Method: fixed multilingual keep-vs-junk text prompts (not per-photo tuned); relevance = mean cosine "
        "similarity to KEEP prompts minus mean cosine similarity to JUNK prompts. Safe threshold = the lowest "
        "score among must/special photos, so this can never lose a must or special photo on this sample "
        "(same structural-conservatism spirit as ADR-021). Baseline: round0_2026-09-27.md M4 junk retention "
        "36/71 = 50.7% (auto filter) / 37/71 = 52.1% (effective).",
        "",
        "## Junk removal at the safe threshold",
        "",
        "**'all'**: threshold is fit AND evaluated on the same labeled sample — an optimistic upper bound, "
        "not the real generalization number. **'held-out'**: threshold from 'all' (fit on the full sample, "
        "which includes the held-out photos) evaluated ONLY on the held-out photos — still not a clean "
        "train/test split (the threshold saw the held-out photos too), but the closer of the two to how this "
        "would behave on unseen photos. A stricter held-out-only refit is future work if this POC proceeds.",
        "",
        "| Model | view | must+special (n) | no (n) | threshold | junk removed | junk retained |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, r in results.items():
        t = f"{r['threshold']:.3f}" if r["threshold"] is not None else "n/a"
        L.append(f"| {name} | all | {r['n_must_special']} | {r['n_no']} | {t} | {r['junk_removed'] or 'n/a'} | {r['junk_retained'] or 'n/a'} |")
        ho = r.get("held_out") or {}
        ht = f"{ho.get('threshold'):.3f}" if ho.get("threshold") is not None else "n/a"
        L.append(f"| {name} | held-out | {ho.get('n_must_special', 'n/a')} | {ho.get('n_no', 'n/a')} | {ht} | {ho.get('junk_removed') or 'n/a'} | {ho.get('junk_retained') or 'n/a'} |")
    L += ["", "## Mean relevance score by worthiness (sanity check: must > maybe > no expected)", "",
          "| Model | must | maybe | no |", "|---|---|---|---|"]
    for name, r in results.items():
        m = r["mean_by_worthiness"]
        L.append(f"| {name} | {m.get('must', float('nan')):.3f} | {m.get('maybe', float('nan')):.3f} | {m.get('no', float('nan')):.3f} |")
    L += ["", "## Caveats",
          "- This report measures a generic, request-independent 'keep vs junk' semantic signal (what M4 junk "
          "retention needs), not per-query precision@K against real owner intents. Real query-based retrieval "
          "evaluation (precision/recall per query, Hebrew+English, pooled grading) is evaluation/retrieval_eval.py "
          "(Curation Lead #1), which imports build_model/embed_images/embed_text from this file. Qualitative "
          "top-K results for two illustrative example queries are in the git-ignored local/ report only (real file names).",
          "- n is small (a few hundred labeled photos from one library) and CPU-only; not a production benchmark.",
          "- The 'safe threshold' is fit and evaluated on the SAME sample (not held-out-only) for this first pass; "
          "re-check on the held-out split alone before trusting the number.",
          ""]
    return "\n".join(L) + "\n"


def held_out_check(photos: list[LabeledPhoto], scores: np.ndarray, results_key: str) -> dict:
    ho_idx = [i for i, p in enumerate(photos) if p.held_out]
    ho_photos = [photos[i] for i in ho_idx]
    ho_scores = scores[ho_idx]
    return safe_threshold_junk_removal(ho_photos, ho_scores, view=f"{results_key}_held_out")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--library", type=int, required=True)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=None, help="cap the number of labeled photos (dry run)")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "reports")
    ap.add_argument("--models", nargs="+", default=list(MODELS), choices=MODELS)
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args(argv)

    settings = Settings()
    conn = connect_ro(a.db or settings.db_path)
    try:
        photos = load_labeled_photos(conn, a.library, a.limit)
    finally:
        conn.close()
    print(f"Loaded {len(photos)} labeled photos for library {a.library}.", flush=True)
    photos, images = load_images(photos)
    print(f"Decoded {len(images)} images.", flush=True)

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "local").mkdir(parents=True, exist_ok=True)
    cache_dir = a.out / "local"

    results: dict[str, dict] = {}
    qualitative: dict[str, list[dict]] = {}
    for model_name in a.models:
        cache = cache_dir / f"emb_{model_name}_lib{a.library}_labeled.npz"
        model = build_model(model_name)
        if cache.exists():
            print(f"Loading cached embeddings for {model_name} from {cache} ...", flush=True)
            z = np.load(cache, allow_pickle=False)
            embeds = z["vecs"]
        else:
            print(f"Running {model_name} (no cache found) ...", flush=True)
            embeds = model.embed_images(images)
            np.savez(cache, vecs=embeds, ids=np.array([p.id for p in photos]))
            print(f"  cached embeddings -> {cache}", flush=True)
        scores = relevance_scores(model, embeds)
        r = safe_threshold_junk_removal(photos, scores, view="all")
        r["mean_by_worthiness"] = mean_by_worthiness(photos, scores)
        r["held_out"] = held_out_check(photos, scores, model_name)
        results[model_name] = r
        qualitative[model_name] = qualitative_topk(model, photos, embeds)
        print(f"  {model_name}: {r}", flush=True)
        # write the report after EVERY model, so a crash mid-run still leaves partial real results
        report = a.out / f"poc_7a_{a.date}.md"
        report.write_text(build_report(a.library, len(photos), results, a.date), encoding="utf-8")
        print(f"  (partial) report written -> {report}", flush=True)

    local = a.out / "local" / f"poc_7a_{a.date}_qualitative.md"
    lines = [f"# 7a POC qualitative top-K (local, git-ignored, real file names) — {a.date}", ""]
    for model_name, items in qualitative.items():
        lines.append(f"## {model_name}")
        for it in items:
            lines.append(f"- **{it['query']}** ({it['text']}):")
            for res in it["results"]:
                lines.append(f"  - {res['file']} (score {res['score']}, label {res['worthiness']})")
    local.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"report: {report}\nqualitative (local, do not commit): {local}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
