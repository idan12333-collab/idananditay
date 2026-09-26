# Cloud task brief: Build-vs-Buy / White-Label research (I-014)

From: Project Manager #1 (local). Status: **awaiting the owner's go**. Research only: no code, no photos, no merge to `main`.

## Hypothesis to test (NOT a decision)
"Build the brain, buy/integrate the rest."
- **Our candidate IP:** natural-language request understanding, library-wide search, people across years, events/time/place, smart selection, duplicates/best shot, diversity/coverage/story.
- **Candidate commodity:** layout, page composition, editor, rendering/PDF, checkout, printing, fulfillment. Only acceptable through a provider that contractually allows white-label/reseller use, with ONE experience under our brand.

## Questions
1. For each commodity layer, which providers offer a real API/SDK/embeddable editor/white-label/reseller program? Verify against CURRENT official developer docs and terms. Never invent capabilities; mark anything unverified as "unverified".
2. For each: what photos/data leave our system (privacy), pricing model if public, supported countries/shipping (including Israel), print specs, integration effort, lock-in/replaceability.
3. The IP-vs-commodity split: confirm or challenge it. Which parts of the "commodity" list are actually differentiating for our customer (e.g. story-aware layout)?
4. Estimated development time saved (a rough range, with stated assumptions) vs. building M6–M9 ourselves.
5. Our existing desk research (I-012): Mixbook Story Mode looks closest. Note what would need hands-on verification.

## Output
- Update `PRINT_INTEGRATION.md` (its existing structure: provider, link, capability, pricing, white-label terms, countries, specs, API/auth, data leaving the system, difficulty, recommendation).
- A new `BUILD_VS_BUY.md`: a per-layer table (build / buy / hybrid), a recommendation, open questions, and what to validate hands-on.
- End with the standard "Handoff to Project Manager" section. Branch only; the PM reviews and merges.

## Constraints
- No roadmap change: recommendations only.
- Desk research ≠ product validation: say so explicitly.
- Keep it concise.
