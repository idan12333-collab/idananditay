# Cloud task brief: M2 model shortlist for the 7a semantic-search POC

From: Project Manager #1. Research only: no code, no photos, a new branch, never main.

## Why
The next product step is the 7a semantic-search POC, evaluated inside the curation framework. Before any model is used, CLAUDE.md requires a license + registry check.

## Task
Shortlist 3–5 candidate image–text embedding models/providers for LOCAL semantic search over personal photos (e.g. CLIP/OpenCLIP variants, SigLIP/SigLIP2, MobileCLIP; others if relevant). For each, verify against official sources:
- code license AND weights license, separately; commercial use allowed?; training-data caveats;
- iPhone feasibility (Core ML / on-device size, latency) and Windows CPU/GPU runtime;
- embedding size, speed per 1,000 photos (published numbers only), memory;
- multilingual/Hebrew query support (important: the owner writes in Hebrew);
- replaceability behind `ImageEmbeddingProvider`.
Mark anything unverified. Don't invent benchmark numbers.

## Output
- Update `MODEL_REGISTRY.md` (status per model: RECOMMENDED_FOR_POC / POC_ONLY / COMMERCIAL_OK / REJECTED, with reasons).
- A short recommendation: which 1–2 models the 7a POC should compare, and why.
- The standard "Handoff to Project Manager" + a 5-line summary for the owner to paste back. Then stop.
