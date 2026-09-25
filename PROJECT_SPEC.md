# Product Specification

## Working name
AI Photo Album

## Problem
People accumulate thousands or tens of thousands of photos. Creating a physical/digital album is painful because the hardest part is not page layout; it is finding the right photos, deciding which are best, removing duplicates, covering important periods/events, and telling a coherent story.

## Product promise
Describe the album you want. The system searches the user's photo library, finds the relevant people/moments, chooses strong and diverse photos, and creates an editable album draft.

## Core use cases
### Person across years
"Make an album of my child from birth in 2018 until today."
Requirements:
- match the intended child across changing ages,
- cover all years reasonably,
- include important events and everyday moments,
- avoid hundreds of similar photos,
- favor good images without erasing meaningful lower-quality moments.

### Relationship
"Make an album of us from 2022 until today."
Requirements:
- prioritize photos containing both requested people,
- also include meaningful contextual photos,
- chronological story.

### Event/trip
"Japan trip."
Requirements:
- infer date/location/event clusters,
- cover locations and days,
- mix people, landscapes, food, activities.

### Theme
"Birthdays and family celebrations."
Requirements:
- semantic search across years,
- group by event/year,
- avoid confusing unrelated cake/party photos where possible.

### Yearbook
"Best of 2026."
Requirements:
- balanced coverage through the year,
- identify events automatically,
- avoid recency or single-event domination.

## User inputs
Required:
- photo library/folder
- natural-language request

Optional:
- date range
- reference people
- people inclusion/exclusion
- approximate number of photos/pages
- chronological vs thematic preference
- style preference
- minimum coverage per year/event

## Outputs
1. Curated photo selection
2. Event/section grouping
3. Ranking/explanations
4. Editable album pages
5. PDF preview/export
6. Machine-readable project JSON

## Non-goals for first MVP
- perfect identity recognition
- automatic commercial printing fulfillment
- native iOS app
- social network
- cloud backup
- video albums
- generative modification of user photos

## Safety/product constraints
- originals are read-only
- no face naming without user input
- no demographic/sensitive-attribute inference
- uncertain identity matches remain uncertain
- user can remove data/project
- external image upload must be explicit and documented

## Monetization hypothesis
Possible later models:
- pay per generated album
- margin on physical printing
- premium subscription for continuous library organization
- family plan

Do not implement monetization before validating curation quality.


## Final commercial product
The final deliverable is a consumer-facing app, not a developer utility.

The user should be able to go from an unorganized photo library all the way to an editable, printable physical photo book without manually exporting and rebuilding the book elsewhere.

### Album editor requirements
- page-by-page visual preview
- configurable album dimensions
- page count
- cover/front/back/spine representation where applicable
- drag/drop or equivalent photo replacement
- crop/reposition
- multiple layout templates
- text/title editing
- warnings for low-resolution print images
- bleed/safe-zone handling
- chronological/thematic reordering
- undoable user edits
- save/resume project

### Print-ready requirements
The renderer must eventually support provider-specific print profiles:
- trim size
- bleed
- safe margins
- DPI/resolution validation
- color/profile requirements when specified
- cover/spine calculations
- page ordering
- export validation

Do not lock the internal album representation to one printing company.

### Fulfillment
Preferred end state: user can press "Order album" and the application submits the validated book to a supported print/fulfillment provider.

Fallback end state: export a validated print-ready PDF/package that can be uploaded to a provider with minimal/no manual redesign.
