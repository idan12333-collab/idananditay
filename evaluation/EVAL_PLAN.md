# Curation Evaluation Plan (DRAFT, Curation & Evaluation Lead #1)

Question: given a large real library and an album request, does the system select the photos the owner actually wants?
Rule: a falsely excluded wanted photo is the most expensive error. No approach is chosen by demo.

## Data
| Set | Where | Purpose |
|---|---|---|
| Seed (~300) | owner library, before the trip | first preferences; the blind reference (SEED_WORKER_BRIEF.md) |
| Owner eval library (1–3k originals) | owner PC | the primary set (LIBRARY_SPEC.md) |
| Itay family library (I-016) | Itay PC only, with Itay's consent | a second set: does the method generalize across families? |
| Held-out (~30% of each, by hash) | inside each set | never used for tuning; the final numbers are reported on it |

Photos never leave the machine they're on. Only aggregate metrics (numbers, no file names) are shared between libraries.

## Metrics (each tied to a label from LABEL_SCHEMA.md)
| # | Metric | Definition | Stage | Target |
|---|---|---|---|---|
| M1 | False exclusion (must) | share of `must` photos the pipeline excludes | candidate | set at baseline; expected ≈0 |
| M2 | Special-moment loss | count of `special` photos excluded | candidate | **0** |
| M3 | Candidate recall | share of `must`+`maybe` that reach ranking | candidate | high; set at baseline |
| M4 | Junk retention | share of `no` photos that reach ranking | candidate | trending down while M1–M3 hold |
| M5 | Duplicate agreement | auto best == owner pick, per group | candidate | set at baseline |
| M6 | Precision@K / acceptance | share of the selected top-K the owner accepts (blind review) | final | per request |
| M7 | Coverage | requested years/events/people represented in the selection | final | per request |
| M8 | Runtime | seconds per 1,000 photos, per stage | all | within the M7 benchmark budget |
| M9 | Label quality | owner override rate on AI proposals; blind vs. shown agreement | labeling | reported, no target |

Each metric is reported with n and a 95% interval (Wilson). Small n is shown as small, not hidden.

## Rounds (each compared with the previous baseline, on held-out)
0. **Baseline**: the current technical filter (M1) on the seed → M1–M5, M8.
1. Semantic relevance (7a POC, M2): M3/M4 + M6 on the query list.
2. People/pets (7b, M3). 3. Events/place/time (M4). 4. Combined curation (M5).

A round "improves" only if its target metric improves AND M1/M2 don't get worse on held-out.

## Baseline procedure (round 0)
1. The seed is labeled (worker + owner).
2. `evaluation/metrics.py` (Curation Lead, read-only DB access) joins curation_labels × the filter outcome (`filtered`/`kept`, primary reason) × duplicate_picks → writes `evaluation/reports/round0_<date>.md`.
3. The report lists every M1/M2 failure with its photo id + reason, for review in the UI. These become the calibration input (blur/brightness/screenshot follow-ups in ROADMAP).

## Retrieval rounds (7a+): per-query search quality
Method and query bank: `queries_template_researched.md` (the owner's; it supersedes `queries_template.md`). Tooling: `evaluation/retrieval_eval.py`. M1–M5 above stay: they measure request-independent filtering, while this section measures "does a request find the right photos". The two lenses are reported side by side.

| Metric | Definition |
|---|---|
| R1 Must-find recall@K | share of the owner's MUST_FIND photos in the top K (K = 20, 50) |
| R2 P@10 | share of the top 10 graded ≥2 (relevant or excellent) |
| R3 nDCG@20 | on the 0–3 grades |
| R4 Hard-negative rate@10 | share of the top 10 the owner flagged as the confusable neighbour (sea↔pool, etc.) |
| R5 Near-dup rate@20 | share of the top 20 that duplicate a higher-ranked result (same duplicate group) |
| R6 he↔en overlap@20 | Jaccard overlap of the top 20 for the Hebrew vs. English wording of the same query |

Ground-truth rules (from the owner's file, enforced by the tooling):
1. Queries are chosen for feasibility with model help, but **MUST_FIND is picked by the owner from a date-browse page, never from model results**, and is frozen before any model is scored.
2. Grades are **pooled**: the top 20 of every model × language, deduplicated and shuffled with the model hidden, graded once. The grades are reused for later models; only unseen results need grading.
3. Everything is keyed by `content_hash` (library IDs are renumbered on re-create, as happened with library 14→15) and stored git-ignored under `reports/local/` (queries may name family members).
4. ~25% of the chosen queries are held out: never used to tune prompts or thresholds.
5. Library 15 spans only 2025–2026, so the time/cross-year queries (G3, D4, "Japan 2026") wait for a larger I-008 library. Rows 9–12 wait for 7b/events.

## Failure-mode log
Every miss is classified: wrongly excluded · junk retained · wrong duplicate · moment missed · too similar · coverage gap · irrelevant to the request. The counts per class go in each round's report.

## Approach comparison record (per candidate model/method)
Quality on the real set · speed · compute/memory · license (MODEL_REGISTRY) · iPhone feasibility · privacy (local?) · replaceability · cost.
