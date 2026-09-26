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

## Failure-mode log
Every miss is classified: wrongly excluded · junk retained · wrong duplicate · moment missed · too similar · coverage gap · irrelevant to the request. The counts per class go in each round's report.

## Approach comparison record (per candidate model/method)
Quality on the real set · speed · compute/memory · license (MODEL_REGISTRY) · iPhone feasibility · privacy (local?) · replaceability · cost.
