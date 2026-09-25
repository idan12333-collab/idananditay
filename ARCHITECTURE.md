# Architecture

## High-level flow
Photo Library
→ Ingestion
→ Metadata/Thumbnail Store
→ Technical Quality + Duplicate Analysis
→ Semantic Embeddings
→ Face Detection/Embeddings
→ Event Clustering
→ Query Retrieval
→ Ranking + Diversity Constraints
→ Album Story Builder
→ Layout Renderer
→ Review UI
→ PDF Export

## Repository target
```text
app/
  api/
  core/
  db/
  ingest/
  vision/
    embeddings/
    faces/
    quality/
    aesthetics/
  retrieval/
  clustering/
  curation/
  album/
  rendering/
  models/
  services/
  web/
tests/
scripts/
data/
  cache/
  thumbnails/
  exports/
```

## Data model draft
### Photo
- id
- source_path
- content_hash
- perceptual_hash
- capture_time
- file_mtime
- width
- height
- mime_type
- gps_lat/gps_lon (optional)
- is_screenshot
- blur_score
- quality_score
- aesthetic_score
- embedding_status
- face_status

### Face
- id
- photo_id
- bounding_box
- embedding reference
- quality/confidence
- person_cluster_id (nullable)

### Person
- id
- user_label
- reference embeddings
- notes

### Event
- id
- start/end
- centroid/location optional
- semantic summary optional

### AlbumProject
- id
- request_text
- constraints JSON
- selected photo IDs
- sections
- layout JSON
- export path

## Model/provider abstraction
Never let business logic call a specific model directly.

Example conceptual interfaces:
```python
class ImageEmbeddingProvider:
    def embed_images(self, images): ...
    def embed_text(self, text): ...

class FaceEmbeddingProvider:
    def detect_and_embed(self, image): ...

class AestheticScorer:
    def score(self, image): ...
```

## Ranking
Start with a transparent weighted score, not an opaque end-to-end model.

Example:
`score = relevance + person_match + quality + aesthetic + uniqueness + coverage_bonus`

Then use constraint-aware selection/MMR-style diversity to avoid repetition.

Weights must be configurable and logged.

## Local-first
For MVP, keep:
- original images local,
- thumbnails local,
- embeddings local,
- SQLite local.

External API calls, if introduced, must be optional adapters and documented.

## Scaling later
Only after validation:
- Postgres
- pgvector/vector DB
- background job queue
- object storage
- cloud GPU inference
- native iOS client
