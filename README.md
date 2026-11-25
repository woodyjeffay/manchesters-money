# Manchester’s Money

An interactive map of foreign ownership in Manchester: which apartment blocks, offices, restaurants, and businesses are ultimately owned or controlled by overseas states, funds, companies, and individuals.

Inspired by the [London Food Money Matrix](http://london-food-money-matrix.vercel.app/).

---

## The core problem

Land Registry records the *legal* owner of a title, which is often a shell company. Foreign money is frequently routed through UK companies (e.g. Manchester Life, the joint venture between Manchester City Council and Abu Dhabi United Group, owns through UK entities) or through offshore vehicles in Jersey, Guernsey, the BVI, and so on. The project’s value is in **walking ownership chains** up to the ultimate controller.

---

## Scope

- **Geography:** Manchester City Council area for v1. Design so Greater Manchester (Salford, Trafford, etc.) can be added later by changing a config value.
- **“Foreign”:** the *ultimate* controller is outside the UK. A Jersey company owned by a UK person is not foreign; a UK company owned by a UAE fund is.
- **Owner types** (one per property):
  - `state` — sovereign wealth funds, state-owned or ruler-linked vehicles
  - `institutional` — foreign pension funds, insurers, asset managers, REITs
  - `corporate` — foreign private companies
  - `individual` — foreign private individuals
  - `unknown` — chain ends in an opaque offshore entity

---

## Data sources

| Source | What it gives us | Access |
|---|---|---|
| HM Land Registry: Overseas companies that own property (OCOD) | Titles in England and Wales whose legal owner is incorporated abroad; address, tenure, price paid, country of incorporation | Free CSV, monthly; I’ll download it to `data/raw/` |
| HM Land Registry: UK companies that own property (CCOD) | Titles owned by UK companies, with company numbers | Free CSV, monthly; I’ll download it to `data/raw/` |
| Companies House API | Company profiles, officers, persons with significant control (PSC), including corporate PSCs and their jurisdictions | Free; needs API key in `.env` as `COMPANIES_HOUSE_API_KEY`; rate limit 600 requests per 5 minutes |
| Register of Overseas Entities (Companies House) | Beneficial owners of overseas entities holding UK land | Free; check what the API exposes for OE numbers |
| FSA Food Hygiene Rating API | Every food business in Manchester with name and address | Free, no key |
| postcodes.io | Postcode → lat/long | Free, no key, bulk endpoint |
| Hand-curated seed file | Known holdings that registers don’t surface cleanly (Manchester Life schemes, City Football Group estate, Etihad Campus, notable sales) | `data/curated/seed.csv`, written by hand with a source URL per row |

Key reading for the curated layer: Goulding, Leaver, and Silver, *Manchester Off-Shored: A Public Interest Report on the Manchester Life Partnership* (University of Sheffield).

---

## Pipeline

Each step is one script in `pipeline/`, reading from and writing to `data/`. Every step must be re-runnable and should cache API responses in `data/cache/` so we never re-fetch unnecessarily.

1. **`01_ocod.py`** — Load OCOD, filter to Manchester. Inspect the actual values in the district/county columns before filtering; don’t assume the spelling. Output `data/interim/ocod_manchester.csv`.
2. **`02_ccod.py`** — Same for CCOD. Output the Manchester rows with company numbers.
3. **`03_geocode.py`** — Geocode all postcodes via postcodes.io (bulk). Log anything that fails.
4. **`04_chains.py`** — For every company number, walk the PSC chain on Companies House:
   - follow corporate PSCs (“relevant legal entities”) upwards;
   - stop at an individual, a state or government body, a foreign entity with no further UK record, or after 8 hops;
   - record the full chain, not just the end point;
   - flag cycles and dead ends rather than crashing.
5. **`05_overseas_entities.py`** — For OCOD owners, look up Register of Overseas Entities beneficial owners where available.
6. **`06_classify.py`** — Assign ultimate country and owner type. Start with rules (jurisdiction, name keywords like “Investment Authority”, “Pension”), then a manual overrides file `data/curated/overrides.csv` that always wins.
7. **`07_food.py`** (phase 3) — Pull FSA establishments for Manchester, fuzzy-match to Companies House, then reuse step 4. Mark match confidence.
8. **`08_build.py`** — Merge registers + curated seed + overrides into `site/data/properties.geojson`. Keep only foreign-controlled properties (plus `unknown`).

---

## Output schema

Each GeoJSON feature:

```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [-2.226, 53.485] },
  "properties": {
    "id": "MAN-000123",
    "name": "Cotton Field Wharf",
    "address": "...",
    "postcode": "M4 6...",
    "property_type": "residential | commercial | hospitality | land | other",
    "tenure": "freehold | leasehold",
    "title_numbers": ["MAN123456"],
    "registered_owner": "Example Ltd",
    "registered_owner_jurisdiction": "UK",
    "ultimate_owner": "Abu Dhabi United Group",
    "ultimate_country": "AE",
    "owner_type": "state",
    "chain": [
      { "name": "Example Ltd", "jurisdiction": "UK", "company_number": "01234567", "source": "https://find-and-update.company-information.service.gov.uk/company/01234567" },
      { "name": "Parent Ltd", "jurisdiction": "UK", "company_number": "07654321", "source": "..." },
      { "name": "Abu Dhabi United Group", "jurisdiction": "AE", "source": "..." }
    ],
    "evidence": "register | inferred | curated",
    "sources": ["https://..."],
    "price_paid": 12500000,
    "last_checked": "2026-11-24"
  }
}
```

---

## Frontend (`site/`)

- Static site, deployable to Vercel. Plain HTML/JS or a light Vite setup; no framework unless needed.
- MapLibre GL (or Leaflet if simpler) on a free basemap.
- Clickable counters by owner type and by country (top five), which act as filters.
- Filters: country, owner type, property type, area.
- Click a pin → side panel showing the property, the full ownership chain step by step, and a source link for every step.
- A “Suggest a correction” form (store submissions somewhere simple; nothing goes live without my review).
- A methodology page explaining sources, limits, and the registered-vs-inferred distinction.

---

## Editorial and legal rules (non-negotiable)

- **Every pin needs a source.** No source, no pin.
- **Separate fact from inference.** “Registered owner” is a fact from the register. “Ultimately controlled by” is our reading of a chain; the UI must say so and show the chain.
- **Never guess.** If a chain ends in an opaque offshore entity, mark it `unknown`; don’t fill the gap.
- **Neutral language.** Describe ownership; don’t characterise it.
- **Attribution.** Include the required HM Land Registry and Companies House licence attributions (Open Government Licence or the dataset’s own licence) in the footer and methodology page.
- **No private individuals’ home addresses.** Only show individuals as ultimate owners of commercial or investment property, and only where the registers name them.

---

## Phases

1. **MVP:** OCOD for Manchester + hand-curated Manchester Life layer → working map deployed.
2. **Chains:** CCOD + Companies House chain-walking + overseas entities → the full property picture.
3. **Businesses:** FSA food businesses matched to owners → restaurants, cafés, and bars.
4. **Polish:** methodology page, corrections workflow, Greater Manchester expansion, monthly refresh script.

---

## Repo layout

```
manchesters-money/
├── README.md
├── .env.example            # COMPANIES_HOUSE_API_KEY=
├── requirements.txt
├── pipeline/               # numbered scripts, one step each
├── data/
│   ├── raw/                # OCOD, CCOD CSVs (git-ignored)
│   ├── cache/              # API responses (git-ignored)
│   ├── interim/            # intermediate outputs (git-ignored)
│   └── curated/            # seed.csv, overrides.csv (committed)
└── site/
    ├── index.html
    ├── methodology.html
    ├── app.js
    ├── style.css
    └── data/properties.geojson
```

