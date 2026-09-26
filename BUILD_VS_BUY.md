# Build vs Buy (I-014) — research recommendation, NOT a decision

> Author: Cloud Worker #1, 2026-09-26. Pending PM review. **Desk research only — not product validation.** Provider facts and sources: `PRINT_INTEGRATION.md`; competitor facts: `COMPETITORS.md`. Nothing here changes the roadmap.

## Verdict on the hypothesis "build the brain, buy the rest"
**Mostly confirmed, with two corrections:**
1. **Layout is split, not commodity.** *Deciding* what goes on each page is story-aware and belongs to the brain: sections, hero vs. supporting photos, chronology, which faces must not be cropped. *Drawing* the pages and exporting a PDF is commodity. Competitors' visible failures (cropped heads, no story structure) sit exactly in the decision part.
2. **The editor is split, not commodity.** The canvas (drag, crop, text, pages) is commodity. The *replace flow* is differentiating: "swap with the alternates from the same event/person", instead of dumping the user back into the whole camera roll (the Popsa complaint). Every competitor is weak here.

## Per layer
| Layer | Build / Buy / Hybrid | Why | Candidate(s) |
|---|---|---|---|
| Request understanding, library search, people across years, events/places, selection, duplicates/best shot, coverage/story | **Build** (our IP) | This is the differentiator. Where the platforms and B2B curation SDKs are strong, measure against them rather than assume we win | — (compare against photobook.ai's SDK, Apple Vision signals) |
| Layout *decisions* (sections, hero, page grouping, safe crop) | **Build** | Story-aware; uses our signals (people, events, coverage) | — |
| Layout *templates/rendering* + PDF export | **Hybrid** | We need our own PDF export anyway (the required fallback, and some print APIs take a PDF). Keep the templates simple | Own HTML/CSS → PDF (WeasyPrint spike), or the editor SDK's PDF export |
| Visual page editor (M8) | **Hybrid** | Buy the canvas engine; build the alternates/swap panel on top | IMG.LY CE.SDK (MAU licence), or a simple own editor for the MVP |
| Print specs / preflight | **Hybrid** | Provider-neutral model (ours) + the provider's product data (cover/spine sizes from its API) | Provider catalog APIs |
| Checkout / payments | **Buy** (later) | Commodity; physical goods. That iOS apps may take their own payments for physical goods (outside Apple IAP) is **unverified**; check the App Store rules | Stripe-like PSP, or a provider's checkout (Peecho) |
| Printing / fulfillment / shipping / tracking | **Buy** | Capital-heavy; mature APIs exist | Shortlist: Gelato, Peecho, Prodigi; also Lulu, Cloudprinter |
| White-label platform (Printbox/Taopix) | **Avoid** | Built for printers, not for an AI-first app; hosted photos; heavy lock-in; duplicates our flow | — |

## Privacy
- Buying print means the **selected** photos (typically 50–300), rendered into the print PDF, and the shipping name/address leave our system. This is unavoidable for printing.
- The library, embeddings and face data never need to leave. Document the provider as an image-data recipient (CLAUDE.md privacy rule).
- Prefer an editor SDK that renders in our app over a hosted editor. IMG.LY's behaviour is **unverified**.

## Development time saved (rough, assumptions stated)
Assumptions: one developer with Claude workers, consumer-quality bar, Israel + one other market. The numbers are order-of-magnitude guesses, not estimates.

| Scope | Build ourselves | With buy/hybrid |
|---|---|---|
| Print production + shipping + tracking + customer service for print defects | Not realistic in-house (a physical operation) | 1–3 weeks per provider integration + test orders |
| Visual editor to consumer quality (M8) | ~2–4 months | ~3–6 weeks (SDK integration + our alternates panel) |
| PDF/preflight/cover-spine per product | ~3–6 weeks | ~1–3 weeks (provider product data + our fallback PDF) |
| Checkout/payments | ~3–6 weeks | ~1–2 weeks |
| **Total M6–M9 "rest"** | **~5–9 months + a print operation** | **~2–3.5 months** → saves roughly **3–6 months** |

## Risks of buying
- **Lock-in:** keep `PrintProvider` and the editor behind interfaces, as already planned in `PRINT_INTEGRATION.md`.
- **Cost per MAU** (editor SDK) and per-book margin: unverified pricing.
- **Print quality/colour:** varies by provider and by the local printer. Only real test books show it.
- **Israel:** no provider confirmed Israel shipping or local production; no Israeli printer API found.
- **B2B curation SDKs** (photobook.ai/muvee): if a printer can buy "good enough" curation, our brain must be measurably better (see `COMPETITORS.md`, target metrics).

## Open questions
1. Which providers ship to Israel, with what delivery time, price and local production?
2. The white-label terms of Gelato, Peecho and Prodigi: our brand only, their name off the package and emails?
3. IMG.LY: MAU price at our scale; does rendering/export run on-device?
4. Do we export our own PDF, or send per-page images the provider composes? This affects preflight ownership.
5. App Store rules for physical-goods payments (verify).

## Validate hands-on (desk research can't answer these)
- Open sandbox/test accounts for 2–3 print APIs (Gelato, Peecho, Prodigi). Place test orders to an Israeli address. Compare quality, colour, delivery time and landed price. Fits I-013 "concierge album".
- An IMG.LY trial: build one page with an alternates panel prototype. Check performance and licence cost.
- A WeasyPrint spike: one spread with full-bleed photos, checked against one provider's spec.
- From I-012: a hands-on Mixbook Story Mode test (does it search the whole library?) and a PhotoKit people-data check.
