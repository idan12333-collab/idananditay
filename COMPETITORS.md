# Competitors (I-012 desk research)

> Author: Cloud Worker #1, 2026-09-26. **Desk research only — not product validation.** No product was tested hands-on. Pending PM review.
> Sources are listed at the end. Confidence per row: HIGH = vendor/official docs, MED = press/reviews, LOW = vendor-competitor blogs or inference.

## Method and limits
- Method: web search only (September 2026). Direct page fetches were blocked by the cloud network proxy, so the facts below come from search-result summaries of official pages, press and reviews. No hands-on testing, no purchases.
- Confidence: HIGH = stated by the vendor/official docs; MED = press/reviews; LOW = vendor-competitor blogs or inference. Pricing is sparse.

## Competitors (customer journey view)
| Product | How the user starts | Who selects photos | NL request | People/time/place/events | Duplicates/quality | Print | Main friction | Conf. |
|---|---|---|---|---|---|---|---|---|
| **Mixbook Story Mode** (US, launched June 2026) | Describe the memory in a few words + upload photos | AI curates the uploaded set, groups moments, writes text, offers 3 finished books | **Yes (prompt → book)** | Groups moments; the iOS app "Memories" builds events from date/location | Uses Apple on-device frameworks for curation + image scoring; LLM for narrative | Integrated (Mixbook prints) | Still "upload your photos": unclear whether it searches the whole library; claims 3.5× faster, half the time to order | MED |
| **Mixbook Memories / Auto-Create** (iOS) | App groups the camera roll into events | AI picks the best shots per event | No | Date/location/burst → events | Best-shot pick | Integrated | iOS only; event-scoped, not multi-year person | MED |
| **Google Photos** | Book from an existing album; suggested books after trips/events | Auto-picks ~40 "best" photos (2017 design) or the whole album | Search: **Ask Photos (Gemini)**, but not "make a book from a prompt" | Strong face grouping, places, trips | Some best-photo selection | Integrated (US print by Fujifilm from Aug 2026) | The user must build/choose the album first; Ask Photos had accuracy complaints and was paused | HIGH/MED |
| **Apple Photos** | "Create a Memory": type a description | AI picks photos + a story arc | **Yes, but produces a movie, not a book** | Strong People, places, events (on-device) | Built-in curation | No first-party books (discontinued); Mac extensions (Motif/Mimeo) with AI curation + autoflow + face-aware crop | Prompt → movie only; the print route is Mac-only via extensions | HIGH/MED |
| **Shutterfly Autofill** | Upload photos; choose all / most / best | AI "best photos" + layout up to 111 pages; AI captions | No | Little | "Best photos" option | Integrated | The user gathers and uploads the photos first | MED |
| **Popsa** | Grant library access; select photos | Auto layout, grouping by time; faces for layout | No | Timestamps, faces, "smart albums" | — | Integrated | The swap flow goes back to the whole camera roll; reports of cropped heads; the user still selects | MED |
| **Chatbooks** | Connect the camera roll / favorites; subscription series | Mostly the user's favorites; ML excludes blurry/dark; "Suggested Books" | No | Little | Blur/dark filter | Integrated (softcover, subscription $15–34) | Grid layouts; curation is shallow | MED |
| **LifeCache** (new) | Monthly upload from the iPhone | AI picks the best, filters screenshots/duplicates, groups events, writes titles | No | Events | Duplicates + screenshots | Yearbook ($50–120/yr incl. credit) | Monthly habit; yearbook-only | LOW (own blog) |
| **CEWE** (EU) | Creator software / app assistant | Assistant auto-distributes photos; app suggests books "from your best pictures" | No | Some | Some | Integrated | Desktop-heavy; the user selects | MED |
| **Picabook AI** (Israel) | App; AI builds an album "without lifting a finger" | Picks the best per event (color/light/focus), recognizes family faces, timeline stories | No evidence | Events on a timeline, faces | Quality-based | Integrated (Israel) | Unknown; direct local competitor | MED |
| **Lupa AI** (Israel) | App | Auto arrangement + smart crop | No evidence | — | — | Integrated | Layout automation, not curation | LOW |
| **photobook.ai / muvee Albumstory SDK** (B2B) | White-label SDK for printers | Quality ranking, duplicate removal, variety, faces, events engine (time/place/faces), safe crop | No evidence | Yes | Yes | Via the printer that licenses it | Any printer can buy "curation" off the shelf | MED (vendor) |
| **Immich** (open source) | Self-hosted library | — (search/organize only) | CLIP NL search | Faces, map | — | No | Technical setup; no album product | HIGH |
| **Pro culling** (Aftershoot, Narrative, FilterPixel, Lightroom Assisted Culling) | Photographer imports a shoot | Burst grouping + best frame (Aftershoot/FilterPixel); Lightroom scores but doesn't group | No | — | Strong duplicate/best-shot handling | No | For pros, per shoot, not lifelong libraries | MED |

## Answers
1. **Done well already:**
   - automatic layout and autoflow (a commodity);
   - event grouping from time/place;
   - face grouping inside Google and Apple;
   - natural-language *search* (Google Ask Photos, Apple, Immich);
   - burst/best-shot picking (pro culling tools);
   - integrated printing;
   - Apple prompt → Memory *movie*;
   - Mixbook prompt → finished book options, from photos the user supplies.
2. **Where manual work remains:**
   - the **initial gathering and selection of photos** (almost every book product starts from uploaded/selected photos or an existing album);
   - long-span requests ("my son 2018–today", "us since 2022");
   - balancing coverage across years/events;
   - fixing crops (cropped heads);
   - swap flows that return to the whole camera roll;
   - verifying the right people;
   - the platform owners (Apple/Google), which have the full library but don't turn a prompt into a *book*.
3. **Already common in our vision:**
   - auto layout;
   - AI captions;
   - event grouping by time/GPS;
   - blur/dark/duplicate filtering;
   - best-shot selection;
   - face-aware crop;
   - print ordering;
   - even prompt-based book creation (Mixbook).
4. **Possibly differentiated (not proven):**
   - (a) a prompt over the **entire library** with no pre-selection;
   - (b) **multi-year person/relationship albums** with reference photos across ages and an "uncertain" state;
   - (c) explicit **coverage/diversity constraints** (per year/event/person) instead of "best photos";
   - (d) **explainable** reasons + measured quality (the evaluation harness);
   - (e) privacy/local processing as a positioning point. Mixbook already runs on-device *analysis*, but uses an LLM for the narrative.

   Risk: Mixbook Story Mode + Apple frameworks may already cover (a) partly on iOS; this is unverified.
5. **Validate early:**
   - what Mixbook Story Mode / Google / Picabook actually do on a real 5k+ library (a hands-on bake-off);
   - whether third-party iOS apps can access Apple's People/face clusters. If not, we must run our own face model while Apple/Google get it for free (**to verify**, PhotoKit);
   - Apple Vision `CalculateImageAestheticsScoresRequest` (free on-device aesthetics + a "utility image" flag) vs our classical scores;
   - buy vs build for layout/curation (B2B SDKs exist).
6. **Measurable advantages to aim for (proposal):**
   1. Time from request to an order-ready book on a ≥5,000-photo library with **zero pre-selection**: ≤10 min of user time.
   2. Photos replaced by the user before ordering: ≤15%.
   3. Recall of user-marked "must-have" photos: ≥90%.
   4. Near-duplicate redundancy in the book: ≤2% of photos.
   5. Coverage: every requested year/event represented; no single day >10% of the book; requested-person precision ≥95% across ages.

   The targets are placeholders to calibrate against a competitor baseline.

## Threats
- **Mixbook Story Mode (2026):** prompt → finished book with integrated printing and Apple on-device curation. This is the closest match to our pitch.
- **Apple and Google:** they own the full library, the people clusters and NL. One feature launch ("make a book from a prompt") would close most of the gap. Apple already does prompt → movie.
- **B2B curation SDKs** (photobook.ai/muvee): they turn curation into a commodity that every printer can license.
- **Picabook AI (Israel):** a local competitor claiming automatic event/face-based selection.

## Opportunities
- **Nobody clearly owns** "whole library → long-span, person-centric, coverage-balanced book from one sentence" with a measured quality level.
- **Swap/review UX is weak everywhere**: the swap goes back to the camera roll, and crops cut off heads. Alternates from the same event ("similar to another selected photo — alternate") are a concrete edge.
- **Partner rather than build print/fulfillment and possibly layout.** Our value is curation.
- **Free on-device Apple signals** (aesthetics, utility-image) for the iPhone path.

## Recommended experiments (for the PM to decide on)
- **E1 Bake-off:** one real library, 3 requests (child multi-year, trip, a year). Run them in Mixbook Story Mode, Popsa, Google Photos and Picabook. Measure minutes, photos replaced, must-haves missed, duplicates and coverage. This is the baseline for the targets above. Needs an iPhone and possibly purchases.
- **E2 PhotoKit check:** what people/face data a third-party app can read. This is documentation research and can run in the cloud.
- **E3 Aesthetics comparison:** Apple Vision aesthetics score vs our classical score on the owner's review labels. Needs a Mac/iPhone + the labels (local).
- **E4 Buy vs build:** photobook.ai/muvee SDK terms/pricing vs our own layout/curation. Cloud research.

## Suggested roadmap implications (suggestions only; the PM/owner decides)
- Add the competitor baseline (E1) to M7 validation, or earlier as a lightweight manual test.
- Treat M4.5 request understanding as table stakes, not a differentiator.
- The differentiation lives in M3 (age-robust people), M5 (coverage/diversity constraints) and the evaluation harness. Consider protecting their priority.
- Pull the buy-vs-build research for layout/print (M6/M9) earlier, since mature SDKs/partners exist.

## Decisions requiring PM/owner approval
- Whether to run E1 (time, an iPhone, possible cost) and E2–E4.
- Whether to commit this report to the repo (location/branch).
- Whether any roadmap implication is adopted.
- Whether "a B2B curation engine for printers" goes to the backlog as an idea.

## Sources
- Mixbook: [Tom's Guide](https://www.tomsguide.com/ai/mixbook-just-launched-an-ai-feature-that-creates-photo-books-from-your-prompts) · [PetaPixel](https://petapixel.com/2026/06/11/mixbook-story-mode-lets-you-describe-how-you-want-a-photo-book-to-look/) · [ProVideo Coalition](https://www.provideocoalition.com/mixbook-launches-story-mode-an-ai-tool-to-make-photobooks-much-more-efficient/) · [Memories help](https://help.mixbook.com/en_us/what-is-the-memories-feature-and-how-does-it-work-ByoqIuksxe)
- Google Photos: [photo book help](https://support.google.com/photos/answer/7378811?hl=en&co=GENIE.Platform%3DDesktop) · [TechRadar](https://www.techradar.com/news/google-photos-can-now-automatically-design-a-physical-photo-book-for-you) · [TechCrunch 2026](https://techcrunch.com/2026/03/10/google-gives-in-to-users-complaints-over-ai-powered-ask-photos-search-feature/) · [DPReview](https://www.dpreview.com/news/the-google-photos-print-store-just-got-a-fujifilm-upgrade-with-new-options-coming-soon/)
- Apple: [Apple Intelligence in Photos](https://support.apple.com/en-ca/guide/iphone/iphf7de217f0/ios) · [MacRumors iOS 27 Photos](https://www.macrumors.com/guide/ios-27-photos-app/) · [Motif](https://mimeophotos.com/our-apps/motif-for-mac/) · [Vision aesthetics](https://developer.apple.com/documentation/vision/calculateimageaestheticsscoresrequest)
- Others: [Shutterfly](https://www.shutterfly.com/ideas/create-a-photo-book-with-ai-in-minutes/) · [Popsa review](https://the-gadgeteer.com/2025/09/26/popsa-smart-photo-book-review-great-app-that-makes-creating-a-photo-book-easy/) · [Popsa Trustpilot](https://www.trustpilot.com/review/popsa.com) · [Chatbooks](https://www.tasteofhome.com/article/chatbooks-review/) · [LifeCache](https://lifecache.ai/) · [CEWE](https://www.cewe.co.uk/tutorials/photo-books/the-assistant.html) · [Picabook AI](https://www.picabook.co.il/HE-IL/picabookai.asp) · [Lupa](https://www.lupa.co.il/general/new-app/) · [photobook.ai](https://photobook.ai/technology/curation/) · [Immich](https://docs.immich.app/features/facial-recognition/) · [Aftershoot](https://aftershoot.com/blog/ai-culling-vs-lr-culling/)
