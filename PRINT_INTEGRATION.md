# Printing & Fulfillment Integration Research

## Goal
Find the best legitimate way for the final application to turn an AI-generated album into a physical printed photo book.

Do not guess. Research current official provider documentation when this milestone begins.

## Provider comparison
| Provider | Official API/SDK | White-label/POD | Photo Book Support | Order API | Shipping Regions | Print Specs | Privacy/Data | Status |
|---|---|---|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | RESEARCH |

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
