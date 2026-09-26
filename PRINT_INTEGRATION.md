# Printing & Fulfillment Integration Research

## Goal
Find the best legitimate way for the final application to turn an AI-generated album into a physical printed photo book.

Do not guess. Research current official provider documentation when this milestone begins.

## Provider comparison (I-014 desk research, Cloud Worker #1, 2026-09-26; pending PM review)
> **Desk research only, not validation.** Official doc pages could not be opened from the cloud (network proxy), so the facts come from search results that cite the vendors' own pages. "unverified" = not confirmed from official docs. No account was opened, nothing was ordered. **Israel shipping and local production are unverified for every provider.**

### Print / fulfillment APIs
| Provider | Official developer link | Capability | Pricing (public) | White-label / reseller | Countries / shipping | Print specs (photo books) | API / auth | Data leaving our system | Difficulty | Recommendation / status |
|---|---|---|---|---|---|---|---|---|---|---|
| **Gelato** | [API docs](https://dashboard.gelato.com/docs/get-started/) | Photo books (soft/hard, 7 formats, up to 200 pages) via one multi-page PDF or per-page raster; catalog, price, quote, order create/cancel, test orders | Per-item price endpoint; pay per order (exact numbers unverified) | POD for sellers under their own brand (the terms need reading) | 250+ partners in 32 countries; "worldwide shipping"; Israel **unverified** | 170 gsm silk; cover dimensions via the API | REST, `X-API-KEY` header; webhooks (order status: created/printed/shipped) | Final print PDF (the selected photos, full resolution) + customer name/address | Low–Medium | **Shortlist** |
| **Peecho** | [Print API](https://www.peecho.com/solutions/print-api) | Photo books (hardcover, softcover, layflat); print API, brandable checkout, order routing | API free; pay per product + shipping | Yes: white-label checkout/emails; used by Polarsteps (travel books) and Resnap | "Almost every country"; Israel **unverified** | HP Indigo, perfect bound; layflat available | REST (auth details unverified) | Print PDF + customer data | Low–Medium | **Shortlist** (a close precedent: Polarsteps) |
| **Prodigi** | [API v4 docs](https://www.prodigi.com/print-api/docs/reference/) | Hardcover (24–500 pages, printable spine), softcover, layflat (18–122 pages); multi-asset orders; product lookup + quote | Per item (numbers unverified) | Dropshipping/POD under the seller's brand | Global (Israel **unverified**) | Must submit the page count; PDFs processed at exact size | REST v4 (auth details unverified) | Print PDF + customer data | Low–Medium | **Shortlist** |
| **Lulu Print API** | [Developer portal](https://developers.lulu.com/) | 3,000+ book configurations incl. hardcover casewrap photo books; interior + cover PDFs | API free; pay per print + shipping | POD for the seller's own brand | 200+ countries (an exclusion list exists; Israel **unverified**) | Casewrap needs ≥0.75 in safety margin; separate cover PDF with spine | REST, sandbox available | Interior + cover PDFs + customer data | Medium (strict PDF specs) | Candidate (strongest for "book" formats; photo-book quality to verify) |
| **Cloudprinter.com** | [Print API](https://www.cloudprinter.com/print-api-restful-json-specifications) | Print network: 381 locations in 104 countries; photobooks among 50k products | Per product (unverified) | Routes to local printers; white-label unverified | 104 countries of local production; Israel **unverified** | Per product | REST/JSON, webhooks, PHP/Node SDKs | Print PDF + customer data | Medium | Candidate (local production could matter for Israel) |
| **Blurb** | [Print API](https://www.blurb.com/print-api-software) | Self Service API (photo books) and Custom API (more formats) | Self Service: no setup/monthly fee, pay per print | Custom API by agreement | **Self Service ships to the US only**; Custom API global via RPI | Blurb specs | REST (details unverified) | Print PDF + customer data | Medium | Not first choice (US-only self-service) |
| Israeli printers (Beeri/Pix, Albume, Zooma, Picabook, Lupa…) | — | Consumer web/app editors | — | — | Israel | — | **No public API found** | — | — | Would need a direct B2B conversation |

### Editor / platform layers (not printers)
| Provider | Link | Capability | Pricing | White-label | Data leaving | Fit |
|---|---|---|---|---|---|---|
| **IMG.LY CreativeEditor SDK** | [CE.SDK](https://img.ly/products/creative-sdk/) | Embeddable photo-book editor (web, iOS, Android), templates, PDF export with bleed/trim/colour profile | By monthly active users; contact sales | Full white-label in commercial licenses | Unverified; our reading is that it runs in our app, but where rendering happens needs checking | **Candidate for the M8 editor** |
| **Printbox** | [Printbox](https://www.getprintbox.com/) | Enterprise white-label web-to-print platform (editor + commerce + production), API, webhooks | Enterprise (unverified) | Yes | Hosted: photos go to their platform | Poor fit: built for printers, heavy lock-in |
| **Taopix** | [Taopix](https://taopix.com/software/) | White-label photobook software for print businesses (editor, commerce) | Unverified | Yes | Hosted | Poor fit (same reasons) |
| **photobook.ai / muvee Albumstory SDK** | [SDK](https://photobook.ai/sdk/) | AI curation + auto layout SDK, safe-crop zones, events engine | Unverified | Yes (white-label) | Runs natively on mobile (per vendor) | A *competitor* to our brain; possibly a layout component. Evaluate carefully |

### Own rendering (build)
- **WeasyPrint** (BSD-3) can produce PDFs with trim/bleed boxes. A known issue is backgrounds clipped at the page edge in bleed setups ([#934](https://github.com/Kozea/WeasyPrint/issues/934)), so it needs a spike. CMYK/ICC handling is unverified. It is only needed for our own PDF export (the required fallback).

### Not integrable
- Mixbook, Shutterfly, Popsa, Chatbooks, CEWE, Google Photos, Apple: consumer products. No public ordering API was found. They are competitors, not vendors.
- No legitimate MCP server for photo-book printing was found. Not needed: the providers above have REST APIs.

## Questions to answer
1. Can we programmatically create/order a multi-page photo book?
2. Can we upload print-ready PDF/pages rather than use the provider's editor?
3. Is there an official API/SDK?
4. Is there a white-label or print-on-demand program?
5. Is API access public or partnership-only?
6. What countries can they fulfill to?
7. What album sizes, covers, papers and page counts are available?
8. What are bleed, safe-zone, DPI, color and spine requirements?
9. Can pricing and shipping quotes be fetched?
10. Can orders and tracking be managed programmatically?
11. What commercial terms apply?
12. What image/customer data must be sent to the provider?
13. Does a legitimate MCP server/connector exist? If yes, what does it actually expose?

## Architecture rule
Create a provider-neutral `PrintProvider` interface. A specific vendor should be an adapter, not embedded throughout business logic.

Conceptual interface:
```python
class PrintProvider:
    def list_products(self): ...
    def get_print_profile(self, product_id): ...
    def validate_album(self, album, product_id): ...
    def get_quote(self, product_id, destination): ...
    def submit_order(self, album_export, customer, destination): ...
    def get_order_status(self, order_id): ...
```

Not every provider will support every method. Capabilities must be explicit.

## Fallback
Even with zero provider APIs, the app must export a validated, page-ordered, print-ready PDF/package so the book does not need to be manually redesigned.
