# Model & Dependency Registry

Claude Code must maintain this file before adopting AI models in the production path.

## AI models

| Capability | Candidate | Code License | Weights License | Commercial? | Data Leaves Device? | Status | Notes |
|---|---|---|---|---|---|---|---|
| Image/text embeddings | TBD | TBD | TBD | TBD | No preferred | RESEARCH | Compare CLIP/SigLIP-family candidates (Milestone 2) |
| Face detection/embedding | TBD | TBD | TBD | TBD | No preferred | RESEARCH | Must support replaceable provider (Milestone 3) |
| Aesthetic scoring | TBD | TBD | TBD | TBD | No preferred | RESEARCH | Avoid relying on beauty score alone |
| Blur/exposure/quality | `ClassicalQualityAnalyzer` (own code: tile Laplacian variance, luminance stats) | project | n/a (no model) | Yes | No | APPROVED_FOR_COMMERCIAL | Heuristic thresholds need calibration on real libraries |
| Near-duplicate hashing | pHash + dHash via `imagehash` | BSD-2-Clause | n/a (no model) | Yes | No | APPROVED_FOR_COMMERCIAL | Deterministic algorithms |

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
- `APPROVED_FOR_COMMERCIAL`
- `REJECTED`

## Rule
Do not mark a model `APPROVED_FOR_COMMERCIAL` without checking both source-code and model-weight terms from authoritative sources.
