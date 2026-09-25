# AI Photo Album — Claude Code Master Instructions

## Mission
Build a commercial-ready MVP for an AI-powered photo curation and album creation product.

The product lets a user point the system at a large personal photo library, describe what album they want in natural language, optionally provide reference photos of important people, and receive a curated, editable album draft made from the most relevant and best-quality photos.

Examples:
- "Create an album of my son from his birth in 2018 until today."
- "Create an album of me and my partner from 2022 until today."
- "Create an album from our Japan trip."
- "Create an album of birthdays and family celebrations."
- "Create a 2026 year-in-review album."

This is NOT just a trip-album app. The core is general-purpose personal-photo search + curation + storytelling + album generation.

## Your role
Act as the senior engineer, product engineer, and technical architect. The user is the product owner and may not be a programmer.

Do not merely explain what code should be written. Inspect the repository, create/edit files, run commands/tests, diagnose failures, and move the project forward.

Keep explanations understandable and concise. When a technical decision is important, explain:
1. what you chose,
2. why,
3. the tradeoff,
4. whether it can be changed later.

## Working rules
1. Read this file, `PROJECT_SPEC.md`, `ARCHITECTURE.md`, `ROADMAP.md`, and `MEMORY.md` before major work.
2. Before coding a new milestone, state a short implementation plan.
3. Work incrementally. Keep the app runnable after each meaningful change.
4. Do not rewrite working components unnecessarily.
5. Prefer simple, testable solutions over premature scale.
6. Never silently fake AI results. If a model/service is unavailable, expose a clear fallback or error.
7. Never commit secrets. Use `.env.example`.
8. Add/update tests for core logic.
9. Update `MEMORY.md` after meaningful decisions or completed milestones.
10. Update `ROADMAP.md` checkboxes as work is completed.
11. Record significant architecture decisions in `DECISIONS.md`.
12. Before declaring a milestone complete, run the relevant tests and report what passed/failed.
13. Context-limit handoff (standing rule): when the conversation approaches the context limit, stop at a safe point — do not leave half-finished edits. Then:
    - make sure all code is saved and the app is still runnable (run the tests if code changed since the last run);
    - update `MEMORY.md` "Current state (session handoff)" with the exact project state: what is done, what is in progress, last test result, last user instruction;
    - update `ROADMAP.md` checkboxes and `DECISIONS.md` as needed;
    - record open issues and the single recommended next action in `MEMORY.md`.
    A new Claude Code session must be able to continue from the files alone, without relying on conversation history. New sessions should start by reading `MEMORY.md` "Current state".

## Privacy first
Personal photos and face embeddings are sensitive.

For the MVP:
- Default to local processing where practical.
- Never upload full photo libraries to third-party APIs without an explicit product decision.
- Store only the minimum derived data required.
- Make data deletion possible.
- Treat face embeddings as sensitive derived data.
- Do not attempt to identify unknown real-world people by name. Face matching is only for grouping/matching people the user intentionally supplies or labels.
- Do not infer sensitive traits from faces/photos.
- Document every external service that receives image data.

## Commercial licensing rule
Do not choose a model/library for the production path solely because it is convenient.

Before adopting any pretrained model:
- identify the code license,
- identify the weights/model license separately,
- confirm whether commercial use is permitted,
- record the source and status in `MODEL_REGISTRY.md`.

If commercial rights are unclear, label it `POC_ONLY` and keep it behind an interface so it can be replaced.

## Product principle
The differentiator is:
"Turn thousands of personal photos into a meaningful album without manually searching and selecting them."

The system must optimize for:
- relevance to the user's request,
- correct people,
- visual quality,
- diversity,
- chronological/story coverage,
- avoiding near-duplicates,
- avoiding over-representation of one event/day,
- user control.

Do NOT optimize only for "prettiest photos."

## MVP scope
Start with a desktop/local web MVP, NOT an iPhone app.

Input:
- a local folder of JPEG/PNG/HEIC photos,
- a natural-language album request,
- optional date range,
- optional 3–10 reference images per person,
- desired approximate album size.

Output:
- searchable/indexed photo library,
- candidate selection,
- ranked/curated selection,
- event/time clusters,
- editable album draft,
- PDF preview/export,
- JSON project file containing selection/layout decisions.

Later:
- iOS PhotoKit integration,
- cloud sync,
- printing partner/API,
- accounts/payments.

## Suggested technical baseline
Use this unless repository constraints justify a change:
- Python 3.12
- FastAPI backend
- SQLite for MVP metadata
- vector index abstraction (start local; keep replaceable)
- Pillow / image decoding helpers
- EXIF extraction
- HEIC support where practical
- perceptual hashing for duplicates
- pluggable image/text embedding provider
- pluggable face detection/embedding provider
- pluggable aesthetic/quality scorer
- HTML/CSS album renderer + PDF export
- simple local web UI

Do not hard-wire the project to a single AI vendor.

## Required interfaces
Design adapters/interfaces for:
- `ImageEmbeddingProvider`
- `FaceEmbeddingProvider`
- `AestheticScorer`
- `ImageQualityAnalyzer`
- `CaptionOrVisionProvider` (optional/enrichment)
- `VectorStore`
- `AlbumRenderer`

This allows models to be swapped as licensing/cost/performance changes.

## Curation pipeline
Implement the pipeline conceptually in this order:

1. Ingest
   - scan folders
   - normalize paths
   - extract dimensions, timestamps, EXIF/GPS if present
   - generate thumbnails
   - compute hashes
   - never modify originals

2. Technical filtering
   - corrupted/unreadable
   - screenshots where detectable
   - extreme blur
   - extremely low resolution
   - exact/near duplicates

3. Semantic indexing
   - image embeddings
   - optional captions/tags
   - natural-language retrieval

4. Person matching
   - detect faces
   - create embeddings
   - reference-person matching
   - support multiple people per image
   - threshold must be configurable
   - retain "uncertain" instead of forcing a match

5. Event grouping
   Use combinations of:
   - capture time,
   - time gaps,
   - GPS/location when available,
   - semantic similarity,
   - burst/near-duplicate relationships.

6. Ranking
   Build an explainable score from separate components:
   - query relevance
   - requested-person relevance
   - technical quality
   - aesthetic score
   - uniqueness
   - event importance/coverage
   - chronological coverage
   - diversity

7. Selection
   Apply constraints so the top N is not dominated by one day/event/person/scene.

8. Story/album generation
   - chronological or thematic sections
   - hero photos + supporting photos
   - layout templates
   - safe crop respecting faces/salient subjects
   - optional titles/captions
   - editable before export

## Evaluation
Build an evaluation harness early.

Create a way for a human tester to mark:
- relevant / irrelevant,
- correct person / wrong person,
- keep / reject,
- duplicate,
- quality issue,
- preferred among a group.

Track at minimum:
- retrieval precision@K,
- person-match precision on labeled samples,
- duplicate reduction,
- percentage of selected photos accepted by human reviewer,
- event/year coverage,
- runtime per 1,000 photos.

The product cannot be judged only by a demo that "looks good."

## Face recognition caution
Children change significantly with age. Do not assume a single reference embedding from one age works across many years.

Design for:
- multiple reference photos from different ages,
- clustering + human confirmation,
- configurable thresholds,
- uncertainty,
- later improvement with user feedback.

## UX target
The user should eventually be able to:
1. choose a library,
2. describe the album,
3. optionally identify important people,
4. choose album length,
5. click Generate,
6. review the chosen photos,
7. swap/remove/add,
8. review pages,
9. export/order.

The AI should show simple reasons when useful:
- "Matched Daniel"
- "Birthday, 2021"
- "High-quality photo"
- "Similar to another selected photo — alternate"

## Definition of MVP success
A test library with thousands of photos can be processed without manual pre-sorting, and a user can make a broad request such as:
"Create an album of this child from 2018–2026, with good coverage of each year and major events"
and receive a curated set that is substantially faster to review than manually searching the library.

## First task when starting from this starter pack
Do NOT attempt the full product at once.

1. Inspect all project files.
2. Create the repository structure.
3. Write a concrete Milestone 1 implementation plan.
4. Build ingestion + metadata + thumbnails + duplicate detection.
5. Add a basic local UI/API to select a folder and inspect indexed photos.
6. Add tests.
7. Run them.
8. Update MEMORY/ROADMAP.
9. Stop and summarize before moving to the next major milestone unless explicitly instructed to continue autonomously.


## End-to-end product requirement — not just photo selection
The final product must become a real consumer application, not merely a photo-ranking script.

The intended end-to-end experience is:
1. User installs/opens the app.
2. User grants access to their photo library (or selects a local/cloud library).
3. User describes the desired album in natural language.
4. User optionally provides/labels reference people.
5. The system searches, filters, groups, ranks and curates the best relevant photos.
6. The system automatically creates a complete multi-page photo book.
7. The user can visually edit the book: replace photos, move/crop them, change page layouts, titles, page count and cover.
8. The system produces print-ready output with exact page order, dimensions, bleed/safe areas, resolution checks and cover/spine requirements where applicable.
9. The user can ultimately order a physical printed album from inside the product, or export a production-ready package/PDF to a print provider.

### Printing / photo-book integration research
Album creation and printing are first-class product requirements.

When we reach the album/printing milestones, actively investigate whether an existing commercial photo-book/printing platform provides:
- public API,
- SDK,
- developer integration,
- print-on-demand API,
- white-label fulfillment,
- order creation API,
- web-to-print integration,
- or another legitimate connector/integration mechanism.

Examples of capabilities to research (do not assume any vendor supports them):
- upload print-ready pages/PDF,
- specify album dimensions/material/cover/page count,
- obtain pricing,
- create an order,
- shipping address and fulfillment,
- order status/tracking.

Do not invent an API, connector, MCP server, partnership or capability. Verify against current official documentation/terms before recommending or implementing it.

If no suitable direct integration exists, the application itself must still be able to generate a standards-compliant print-ready album package/PDF so that a printing workflow can be connected later.

### Build vs integrate
For every major album-production capability, evaluate:
A. build it ourselves,
B. integrate an existing API/SDK/service,
C. hybrid approach.

Record the comparison in `PRINT_INTEGRATION.md`, including:
- provider/service
- official developer/API link
- capability
- pricing if publicly available
- commercial/white-label terms
- supported countries/shipping
- print specifications
- API/SDK/auth method
- whether user photos leave our system
- integration difficulty
- recommendation/status

### MCP clarification
MCP is only an integration protocol and is not assumed to be the printing engine. If an appropriate MCP server genuinely exists for a required service, it may be considered, but prefer the provider's supported API/SDK. Never invent an MCP connector.

### Final application target
The long-term deliverable is a polished application containing:
- photo-library connection/import,
- natural-language album request,
- person/reference-photo workflow,
- AI search and curation,
- event/timeline organization,
- album generation,
- visual page editor,
- cover editor,
- page-order editor,
- print specification validation,
- PDF/print package export,
- print-provider/order integration where feasible,
- project save/resume,
- privacy controls and deletion.

The architecture created during the MVP must not block this final target.
