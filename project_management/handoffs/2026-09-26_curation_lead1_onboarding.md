# אחראי בקרת איכות תמונות #1 (Curation & Evaluation Lead #1) — onboarding interview

Session: cloud (claude.ai/code), branch `claude/sweet-goldberg-iyncw4`, base `4e68307`. Category: Cloud Worker rules apply (own branch, never `main`, PM = hub, handoff at the end of each task).
Step 0 (cwd): cloud container, not the owner's PC folder — cannot switch. Consequence: I never see real photos or any DB. That fits this role's first step (methodology docs); anything that needs real photos runs on Itay's/Idan's machine.

1. **Task.** Own curation quality + evaluation methodology. First deliverables (docs only, no product code):
   a) eval plan (rounds, baseline, held-out split, metrics mapped to the 12 "Curation gate evidence" items);
   b) I-008 library composition spec (1–3k originals, quotas per category, correct iPhone export checklist, junk types);
   c) label schema — small critical set, OBJECTIVE (duplicate+preferred copy, screenshot/document, technical issue) vs SUBJECTIVE (special moment, keep-worthy, 5-level include scale) with AI suggestion + confidence only; request-independent labels on the full set, relevance labels only for 2–3 test requests; I-017 guards (blind held-out ~10%, proposer ≠ model under eval, correction-rate log); mapping onto the existing `review_labels` / filter-review screen ("מה הסינון הציע?") and what would need schema v5 (NOT reserved yet — would ask the PM);
   d) finalize `evaluation/queries_template.md` (6 query types, 2–3 of them marked as the "album requests" for gate items 6/8).
   Then, later and separately: the baseline round on the current filter.
2. **Files I expect to touch.** New: `evaluation/EVAL_PLAN.md`, `evaluation/LIBRARY_SPEC.md`, `evaluation/LABEL_SCHEMA.md`. Edit: `evaluation/queries_template.md`. Handoff notes in `project_management/handoffs/`.
3. **Must not touch.** `app/`, `tests/`, schema, ADR numbers, ROADMAP/ACTIVE_WORK/WORKERS/MEMORY/DECISIONS (PM-owned — I propose text in my handoff), `main`, W2's local-only exclusions work. No model adoption, no external AI service, no real photos.
4. **Done =** the 4 docs on my branch, each consistent with ADR-018/ADR-021 and the gate list; a handoff with open questions for the owner; PM reviewed/merged.
5. **Test plan.** Docs only → the suite is untouched (I will not run it unless a file outside `evaluation/`/handoffs changes). Self-check: every gate item 1–12 maps to a metric + a label in the schema; every label maps to an existing field or is explicitly marked "needs v5".
6. **Conflicts.** None with code workers (I own only `evaluation/`). Possible overlap: I-016 (Itay's second library) uses the same spec — I will write the spec so it serves both. Schema v5 / ADR-022 only via PM reservation.
7. **Context limits.** Read only: ACTIVE_WORK gate section, ROADMAP curation track, IDEAS I-008/I-016/I-017, ADR-018/021, `review_labels` DDL. No transcripts, no screenshots, no test runs for docs. One commit per deliverable batch.
8. **Stop and ask when:** a label needs a schema change; a metric target needs an owner number; anything implies sending photos off-machine; the "people & animals only vs. trips/landscapes" question affects the composition quotas; I-016 (Itay's library) is not yet approved.

**Waiting for:** PM confirmation/corrections before writing a–d.
