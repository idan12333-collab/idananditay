# Label Schema: curation ground truth (DRAFT, Curation & Evaluation Lead #1)

Status: draft for PM/owner approval. Storage needs schema v5 + ADR-022 (reserved via the PM, not yet used).

## Principles
1. **Only owner-confirmed labels are truth.** AI proposals live in a separate table and are never read as labels.
2. **Preference ≠ technical correctness.** `review_labels` (ADR-018) answers "was the filter's technical decision right?". Curation labels answer "does the owner want this photo?". They are separate fields and are never merged.
3. **Keyed by `content_hash`**, the same as review_labels and duplicate_picks, so labels survive rescans. `rel_path` + `capture_time` are stored too, so labels can be remapped if the same photo is re-imported as a different file (e.g. previews → originals).
4. **A small label set.** Every label must feed a metric in EVAL_PLAN.md; otherwise it isn't collected.
5. **Objective vs. subjective.** For objective labels, the AI may give a verdict that the owner confirms. For subjective labels, the AI may only show a suggestion + confidence, and never on blind items.

## Request-independent labels (whole eval set)
| Label | Type | Values | Kind | How it's collected |
|---|---|---|---|---|
| `worthiness` | required | `must` / `maybe` / `no` | subjective | keys 1/2/3 in quick labeling |
| `special` | optional flag | 0/1 | subjective | key S |
| technically poor but important | **derived** | worthiness ∈ {must, maybe} AND any auto technical flag | — | no click |
| duplicate preferred copy | existing | `duplicate_picks` | objective | existing side-by-side pick |
| screenshot / document | existing + derived | review_labels reason `screenshot` / `not_a_photo` | objective | existing filter review |
| technical verdict | existing | review_labels good/bad | objective | existing filter review |

The ROADMAP 5-level scale (definitely/probably include, neutral, probably/definitely exclude) collapses to 3 levels: `must` = definitely, `maybe` = probably + neutral, `no` = probably/definitely exclude. Reason: faster, and humans are inconsistent on 5-level scales. It can be widened later if the metrics need it.

## Per-request labels (only the 2–3 test requests, later)
`request_relevance(request_id, content_hash, relevance ∈ {relevant, partial, irrelevant})`. People/pet identity labels wait for 7b.

## Metadata stored per label
`source` (`owner` only for truth) · `blind` (1 = no AI suggestion was shown) · `held_out` (1 = never used for tuning; deterministic from the hash, ~30%) · `stratum` (the sampling bucket, see EVAL_PLAN) · `library_key` (owner / itay, see I-016) · `created_at` / `updated_at`.

## AI proposals (I-017, later)
A separate table `ai_label_proposals(content_hash, label, value, confidence, model_id, model_version, created_at)`.
- The proposer model must NOT be the model under test in that round.
- The owner's override rate = the share of shown proposals the owner changed, reported per label.
- 10% of items are shown without a proposal (`blind = 1`). Owner labels on those items are compared with the proposal (hidden at label time) to measure anchoring.

## Proposed v5 DDL (for the implementation worker, after the ADR-022 approval)
```sql
CREATE TABLE IF NOT EXISTS curation_labels (
    content_hash TEXT PRIMARY KEY,
    worthiness   TEXT NOT NULL CHECK (worthiness IN ('must','maybe','no')),
    special      INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'owner',
    blind        INTEGER NOT NULL DEFAULT 1,
    held_out     INTEGER NOT NULL DEFAULT 0,
    stratum      TEXT,
    rel_path     TEXT,
    capture_time TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_label_proposals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    label        TEXT NOT NULL,
    value        TEXT NOT NULL,
    confidence   REAL,
    model_id     TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
```
Additive only (`CREATE TABLE IF NOT EXISTS`); the migration backup (I-004) applies. Deleting a library must not delete labels, because they're keyed by content. A "delete all my labels" action is needed for privacy.
