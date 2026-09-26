# Model & Dependency Registry

Claude Code must maintain this file before adopting AI models in the production path.

## AI models

| Capability | Candidate | Code License | Weights License | Commercial? | Data Leaves Device? | Status | Notes |
|---|---|---|---|---|---|---|---|
| Image/text embeddings | See "Image–text embedding shortlist (M2 / 7a)" below | — | — | — | No (local) | RESEARCH | Shortlist 2026-09-26 (Cloud Worker #1), pending PM review |
| Face detection/embedding | TBD | TBD | TBD | TBD | No preferred | RESEARCH | Must support replaceable provider (Milestone 3) |
| Aesthetic scoring | TBD | TBD | TBD | TBD | No preferred | RESEARCH | Avoid relying on beauty score alone |
| Blur/exposure/quality | `ClassicalQualityAnalyzer` (own code: tile Laplacian variance, luminance stats) | project | n/a (no model) | Yes | No | APPROVED_FOR_COMMERCIAL | Heuristic thresholds need calibration on real libraries |
| Near-duplicate hashing | pHash + dHash via `imagehash` | BSD-2-Clause | n/a (no model) | Yes | No | APPROVED_FOR_COMMERCIAL | Deterministic algorithms |

## Image–text embedding shortlist (M2 / 7a semantic-search POC)
> Desk research by Cloud Worker #1 (2026-09-26), pending PM review. **Not validated on our photos.** Model cards and licence files could not be opened directly from the cloud (network proxy). Facts come from search results quoting Hugging Face / GitHub / arXiv. "unverified" = not confirmed from the primary text. No benchmark numbers are invented. Where none were found, the cell says so. **A legal read of the actual licence files is still required before any commercial release.**

| Candidate | Code licence | Weights licence | Commercial? | Training-data caveat | iPhone feasibility | Windows runtime | Embedding dim / size | Speed (published only) | Hebrew queries | Status | Reason |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **SigLIP 2** (Google), e.g. `siglip2-base-patch16-224/256`; larger `so400m` | Apache-2.0 (big_vision; the per-repo text is unverified) | **Apache-2.0** (HF model cards) | Yes by licence | WebLI (Google, not public): 10B images, 12B alt-texts, **109 languages** (90% English / 10% other) | Good: a community Core ML conversion of `siglip2-base-patch16-256` exists (INT8/fp16, image tower on the Neural Engine) — third-party, unverified | PyTorch/transformers CPU or GPU; ONNX export possible (unverified) | base ≈86M params (vision); 768-d (per the Core ML conversion card); So400m 400M | Community Core ML: ~5 ms/image on an **M5 Pro Mac**, not an iPhone (third-party). No official per-1,000 numbers found | **Designed multilingual** (Gemma 256k tokenizer). The paper reports strong 36-language XM3600 retrieval; the per-language Hebrew score is unverified | **RECOMMENDED_FOR_POC** (+ COMMERCIAL_OK pending a legal read) | Cleanest licence + multilingual + an on-device path |
| **OpenCLIP multilingual** — `xlm-roberta-base-ViT-B-32` (laion5b), or the heavier `CLIP-ViT-H-14-frozen-xlm-roberta-large-laion5B` | MIT (open_clip) | **MIT** (LAION HF cards) | Yes by licence, **but** | Cards say "research output". LAION-5B provenance risk (the dataset was withdrawn in 2023 over illegal-content findings; Re-LAION later) | B/32 plausible via Core ML conversion (unverified); ViT-H too heavy for the phone | CPU/GPU PyTorch | B/32 ≈512-d (unverified); H/14 1024-d (unverified) | None official. Immich ships the XLM-R H/14 variant as its multilingual option | XLM-R text tower covers ~100 languages incl. Hebrew. Published multilingual evals don't list Hebrew; quality unverified | **POC_ONLY** | Good multilingual baseline; data provenance blocks production without review |
| **OpenAI CLIP** ViT-B/32 / ViT-L/14 | MIT | MIT (repo) | Licence allows it, **but** the model card says "any deployed use… is currently out of scope" | Undisclosed web data | Many Core ML ports (unverified) | CPU/GPU | B/32 512-d | None official | **English only** | **POC_ONLY** | English-only baseline; model-card caveat |
| **MobileCLIP (v1)** S0–S2, B (Apple) | Apple licence (repo `LICENSE`, ASCL-style; text not read) | `apple-ascl` (Apple Sample Code Licence, per the HF cards); **terms not read** | Possibly (ASCL is generally permissive): **unverified** | DataCompDR (reinforced DataComp) | **Best**: Apple publishes official Core ML weights (`apple/coreml-mobileclip`) | CPU/GPU PyTorch | S2 ≈512-d (unverified) | Apple reports mobile latency in the paper (numbers not copied here) | **English only** (unverified; no multilingual claim found) | **POC_ONLY** (candidate for iPhone later if English-only is acceptable, and after reading ASCL) | Fast on-device, but no Hebrew |
| **MobileCLIP2** (Apple, 2025) | ASCL | **Apple ML Research Model TOU** (`LICENSE_MODELS`, "apple-amlr"): research purposes | **No** (research use) | DFN/DataCompDR | Official Core ML path | — | — | — | English only (unverified) | **REJECTED** | Research-only weights |
| **jina-clip-v2** | — | **CC BY-NC 4.0** (commercial only via Jina's paid API) | No (local) | — | — | — | 1024-d (truncatable) | — | 89 languages | **REJECTED** | Non-commercial locally; the API would send photos off-device |
| **nomic-embed-vision v1.5** | — | **CC BY-NC 4.0** on the official listing (some README revisions say Apache-2.0 — conflicting) | No (as listed) | — | — | — | shares a space with nomic-embed-text | — | Unverified | **REJECTED** (re-check if re-licensed) | Licence conflict / non-commercial |
| `sentence-transformers/clip-ViT-B-32-multilingual-v1` | Apache-2.0 | Apache-2.0 (distilled text encoder) + OpenAI CLIP image encoder | Text: yes; image tower inherits the CLIP card caveat | Distilled from English CLIP | Plausible (small) | CPU | 512-d | None | "50+ languages"; **Hebrew not confirmed** | **POC_ONLY** (fallback only) | Older approach; Hebrew unconfirmed |

**Replaceability:** all candidates fit `ImageEmbeddingProvider` (`embed_images`, `embed_text`, `dimension`). Embeddings from different models are **not interchangeable**: switching models means re-indexing the library. The `VectorStore` must store the model id + version with every vector.

**Not recommended for local search:** cloud embedding APIs (they send photos off-device; they need a separate privacy decision).

### Recommendation for the 7a POC (for the PM to decide)
Compare **two** models on the same labelled sample, with Hebrew **and** English queries (precision@K):
1. **SigLIP 2 base** (patch16, 224/256): the primary candidate. Apache-2.0 weights, multilingual by design, a proven Core ML path for the later iPhone app.
2. **OpenCLIP `xlm-roberta-base-ViT-B-32` (laion5b)**: the multilingual baseline. MIT, but POC_ONLY because of LAION data provenance. It shows whether SigLIP 2's Hebrew is actually better.

Optional third run, English queries only: MobileCLIP-S2, to measure the iPhone speed/quality trade-off. If Hebrew quality is weak in both, test "translate the query to English, then search" (text only; the roadmap allows sending request *text* out, but a local translator is preferable).

## Third-party libraries (Milestone 0–1)

License status from package metadata as installed (2026-09-26). Re-verify before a commercial release.

| Library | Purpose | License | Commercial? | Status | Notes |
|---|---|---|---|---|---|
| FastAPI / Starlette | HTTP API | MIT / BSD-3 | Yes | OK | |
| uvicorn | ASGI server | BSD-3 | Yes | OK | |
| pydantic / pydantic-settings | config, validation | MIT | Yes | OK | |
| Pillow | image decoding/thumbnails | MIT-CMU (HPND) | Yes | OK | |
| numpy | metrics, vectorized Hamming | BSD-3 | Yes | OK | |
| imagehash (+ scipy, PyWavelets) | perceptual hashes | BSD-2 (+ BSD-3, MIT) | Yes | OK | |
| **pillow-heif** 1.8.0 | HEIC/HEIF decoding | Source BSD-3, but per its bundled `LICENSES_bundled.txt`: **"License for pillow-heif binary wheels: GPLv2"** (bundles libheif + libde265 LGPL-3, x265 GPL-2) | **No for closed-source distribution without review** | **POC_ONLY** | Fine for local POC use. Before shipping a packaged commercial app: legal review of bundled codecs + HEVC patent licensing. Isolated in `app/ingest/imaging.py` (optional import; app runs without it). On iOS the native PhotoKit decoder replaces it. |
| pytest, httpx | tests only | MIT / BSD-3 | n/a (not shipped) | OK | |

## Status values
- `RESEARCH`
- `POC_ONLY`
- `RECOMMENDED_FOR_POC` (shortlisted for a POC comparison; not a production approval)
- `COMMERCIAL_OK` (licence permits commercial use per desk research; still needs a legal read before `APPROVED_FOR_COMMERCIAL`)
- `APPROVED_FOR_COMMERCIAL`
- `REJECTED`

## Rule
Do not mark a model `APPROVED_FOR_COMMERCIAL` without checking both source-code and model-weight terms from authoritative sources.
