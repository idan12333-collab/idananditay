# Handoff to Project Manager — Cloud Worker #1: I-012 storage + I-014 build-vs-buy (2026-09-26)

- **Branch/commit:** `claude/cw1-build-vs-buy`, based on `main` = `94f43f6`. Not merged. The commit hash is in `git log origin/claude/cw1-build-vs-buy -1`.
- **What changed (docs only):**
  - `COMPETITORS.md` (new): the I-012 desk research. Previously only in my session and in a PR #1 comment.
  - `BUILD_VS_BUY.md` (new): per-layer build/buy/hybrid, recommendation, rough time saved, risks, open questions, hands-on validation list.
  - `PRINT_INTEGRATION.md`: the empty "Provider comparison" table replaced with the print-API, editor/platform and own-rendering findings. The rest of the file is unchanged.
  - This note.
- **Tests/research performed:**
  - Web search only. Direct fetches of vendor docs were blocked by the cloud proxy, so every fact comes from search results that cite the vendors' pages.
  - No accounts, no orders, no code, no tests run (docs only).
- **Assumptions:**
  - The time-saved ranges assume one developer with Claude workers and a consumer-quality bar. They are orders of magnitude.
  - Provider capabilities are as described on their current public pages.
- **Unresolved issues:**
  - Israel shipping and local production: **unverified for every provider**; no Israeli printer API found.
  - Pricing: mostly unverified.
  - White-label terms: not read in full.
  - IMG.LY: pricing and whether it renders on-device.
  - App Store rules for physical-goods payments.
  - WeasyPrint bleed handling (a known issue).
- **Dependencies/conflicts:**
  - None with W2 or code.
  - Touches `PRINT_INTEGRATION.md` (research doc).
  - `PRINT_INTEGRATION (1).md` is still a stale duplicate. Not touched; the owner or PM may delete it.
  - WORKERS.md not edited: registering "Cloud Worker #1" is the PM's call.
- **Recommended next action:** the PM reviews this branch. If the direction is accepted, run the hands-on validations in `BUILD_VS_BUY.md`. Test orders from 2–3 print APIs to Israel fit naturally with I-013 "concierge album".
- **Requires PM approval:**
  - merging;
  - whether the hypothesis update goes into IDEAS.md I-014 ("layout and editor are split, not pure commodity");
  - any hands-on test (accounts, costs);
  - any roadmap consequence (e.g. moving the print/editor decisions earlier).

## Summary for the owner to paste to the PM (5 lines)
1. Cloud Worker #1 done: branch `claude/cw1-build-vs-buy` (docs only, not merged); I-012 now saved as `COMPETITORS.md`.
2. I-014: "build the brain, buy the rest" mostly holds, but layout *decisions* and the swap-with-alternates editor flow are ours; the canvas, PDF and printing are commodity.
3. Print APIs worth a shortlist: Gelato, Peecho (used by Polarsteps), Prodigi; also Lulu and Cloudprinter. White-label platforms (Printbox/Taopix) are a poor fit.
4. Buying saves roughly 3–6 months of M6–M9 work (rough guess), but Israel shipping/local production and pricing are unverified for all providers.
5. Next (PM decides): test orders to Israel from 2–3 providers + an IMG.LY editor trial; all findings are desk research, not validation.
