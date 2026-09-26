# Handoff to Project Manager — Cloud Worker #1: M2 model shortlist (2026-09-26)

- **Branch/commit:** `claude/cw1-m2-model-shortlist`, based on `main` = `4e68307`. Not merged. The commit hash is in `git log origin/claude/cw1-m2-model-shortlist -1`.
- **What changed (docs only):**
  - `MODEL_REGISTRY.md`: the embeddings row now points to a new section, "Image–text embedding shortlist (M2 / 7a)". It covers 8 candidates: code and weights licences, commercial status, data caveats, iPhone and Windows feasibility, size, published speed, Hebrew, status and reason. The section adds a replaceability note and a POC recommendation.
  - Two status values added, as the brief asked: `RECOMMENDED_FOR_POC` and `COMMERCIAL_OK`.
  - This note.
- **Research performed:**
  - Web search only. Hugging Face, GitHub licence files and the vendor docs could not be opened from the cloud (proxy), so licences come from search results quoting the model cards and licence files.
  - No code, no downloads, no benchmarks run.
- **Findings:**
  - SigLIP 2: Apache-2.0 weights, multilingual (WebLI, 109 languages), a community Core ML port exists. → RECOMMENDED_FOR_POC.
  - OpenCLIP XLM-R: MIT, but LAION-5B provenance risk. → POC_ONLY.
  - OpenAI CLIP: MIT, but the model card says deployed use is out of scope, and it's English only. → POC_ONLY.
  - MobileCLIP v1: ASCL, the best iPhone path, English only. → POC_ONLY.
  - Rejected: MobileCLIP2 (research-only weights), jina-clip-v2 and nomic-embed-vision (CC BY-NC).
- **Assumptions:**
  - The search summaries reflect the current model cards.
  - "ASCL is generally permissive" is **not** confirmed for MobileCLIP; the terms were not read.
- **Unresolved issues:**
  - Per-language Hebrew retrieval quality: no published number found for any model. Measure it in 7a.
  - No official per-1,000-photo speed numbers found. The only number (~5 ms/image) is third-party and on a Mac, not an iPhone.
  - The exact licence texts still need a legal read before production.
  - Whether Hebrew is in SigLIP 2's WebLI language list: unverified.
- **Dependencies/conflicts:**
  - None with code or W2.
  - `MODEL_REGISTRY.md` is a shared doc; if the PM edited it locally, merge by hand.
  - Any model download in 7a needs the network in the environment where it runs.
- **Recommended next action:**
  - The 7a POC compares **SigLIP 2 base** against **OpenCLIP `xlm-roberta-base-ViT-B-32`** on one labelled sample, with Hebrew and English queries, measuring precision@K and runtime per 1,000 photos.
  - Optional: MobileCLIP-S2 on English queries only.
- **Requires PM approval:**
  - merging;
  - adopting the two new status values;
  - the 7a model pair;
  - any model download or use on real photos (local only).

## Summary for the owner to paste to the PM (5 lines)
1. Cloud Worker #1 done: branch `claude/cw1-m2-model-shortlist` (docs only, not merged); MODEL_REGISTRY.md now has an 8-model embedding shortlist.
2. Recommended for the 7a POC: SigLIP 2 base (Apache-2.0 weights, multilingual, Core ML path) vs OpenCLIP XLM-R B/32 (MIT, but POC_ONLY because of LAION data).
3. POC_ONLY: OpenAI CLIP (model-card caveat, English only), MobileCLIP v1 (fast on iPhone, English only, licence not read), multilingual-v1 fallback.
4. Rejected: MobileCLIP2 (research-only), jina-clip-v2 and nomic-embed-vision (non-commercial).
5. Unverified: Hebrew quality (no published numbers; measure in 7a), speed per 1,000 photos, and the exact licence texts (legal read before production).
