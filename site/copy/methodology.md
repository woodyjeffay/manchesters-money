<!--
  The "About the data" page. Edit on GitHub: open this file, click the pencil
  icon, change the text, then "Commit changes".

  Formatting: "## " starts a section heading. A line starting "- " is a bullet;
  "1. " is a numbered step. **bold**, *italic*, and [link text](https://address).
-->

## About

Manchester has grown fast, and much of the money behind that growth has come from abroad. Sovereign wealth funds, overseas investment firms, and individuals living outside the UK own apartment blocks, offices, hotels, and restaurants across the city.

Who owns this property is often hard to see. Many holdings sit behind chains of companies, some registered in offshore jurisdictions that disclose little about their owners. Some of the money comes from states with poor human rights records. And owners based abroad can be harder to hold to account than those who live here.

This project uses public registers to show who ultimately controls property and businesses in Greater Manchester and Salford, so that you can see for yourself.

“Foreign” here refers to the *ultimate* controller, not the company on the title. A Jersey company owned by a UK resident is not counted as foreign. A UK company owned by an overseas fund is.

This project was built by [Woody Jeffay](https://www.linkedin.com/in/woody-jeffay-682622135/)

## Registered owner and ultimate controller

Every entry separates two things:

- **Registered owner**: the company named as proprietor on the HM Land Registry title. This is a fact taken directly from the register.
- **Ultimately controlled by**: our reading of the chain of companies and people recorded as having control. This is an inference. Each step in the chain is shown with a link to the record it comes from, so readers can check it.

## How chains are built

1. We take every title in the council areas covered from the Land Registry’s datasets of property owned by overseas companies (OCOD) and by UK companies (CCOD).
2. For an overseas company, we find its entry in the Register of Overseas Entities at Companies House and read its registered beneficial owners.
3. For a UK company, we read its “persons with significant control” (PSC) at Companies House. Where the controller is another UK company, we follow that company’s PSCs in turn.
4. We stop at a named individual, a state or government body, an overseas company with no further UK record, or after eight steps. Loops and dead ends are flagged, not guessed past.
5. Where a person or company holds control jointly with others, the entry says so.

## Owner types

- **State-linked**: sovereign wealth funds, state-owned companies, and vehicles owned by members of ruling families.
- **Institutional**: overseas pension funds, insurers, asset managers, and listed property funds.
- **Corporate**: overseas private companies.
- **Individual**: private individuals living outside the UK. Those with small holdings are not named; see below.
- **Unknown**: the chain ends in an entity, usually in an offshore jurisdiction, whose owners are not disclosed, or no beneficial-owner record could be found.

A person is treated as being outside the UK by where they live, as recorded in the register. Nationality plays no part: a foreign national living in Manchester is not on the map, and a British citizen living abroad who controls property here is. Where the register gives no country of residence, the property is not shown.

## Hand-curated entries

Some holdings are not visible in the registers, for example where property is held through joint ventures or long leases. These are added by hand from published sources such as company announcements, council documents, academic research, and the property press. Each carries at least one source link and is marked “curated”. Entries still being checked are marked “awaiting review”.

## Food and drink businesses

An optional layer shows restaurants, cafés, takeaways, pubs, hotels, and supermarkets from the Food Standards Agency’s hygiene register whose operating company is controlled from outside the UK. The hygiene register records a trading name, not the company that runs the business, so we search Companies House for that name. We only accept a company whose name is exactly the trading name once words like “Limited” are removed, and only if it is the one active company with that name, or its registered office is at the business’s address. The panel says which.

These are businesses, not property: the operator may rent its premises from someone else. Where one company trades at several places, some branches of the brand may be run by franchisees.

## Locations

Properties are placed using their postcode (via postcodes.io). Where the register gives no postcode, the address is located using OpenStreetMap and the entry is marked as approximate. Titles that cannot be placed are not shown.

## Individuals and small owners

Individuals are shown only as the owners of commercial or investment property, and only where a public register names them. Homes held through a company, for example a flat owned by an overseas company, are treated as investment property. We do not show property that individuals hold in their own name.

We name an individual only if they meet at least one of these tests:

- they control five or more titles in the areas covered;
- the registered prices of their titles total £5 million or more;
- they control a whole hotel, pub, office, or shop building;
- they run five or more of the food and drink businesses on the map;
- they are named as the owner in a published source we cite, or are a public figure.

Everyone else, typically someone who owns one or two flats through a company, appears as “Private individual” with their country of residence. Their property still counts in every total, because the pattern matters even where the person does not. The company on the title and the Companies House records behind it are still linked, so anyone can check the entry. But we do not print the person’s name, list them under “Top owners”, or let readers search for them. The registers remain public; we have chosen not to gather a small owner’s property into one place under their name.

Companies, funds, and state bodies are named whatever the size of their holding.

## Limits

- Companies House does not verify the information companies file. Records can be incomplete, out of date, or wrong.
- Some overseas entities that hold land have not registered as required, or are registered under a slightly different name. These appear as “unknown”.
- The Land Registry datasets cover company-owned titles only. They do not include property owned by individuals in their own name.
- Ownership changes. Each entry shows the date it was last checked.
- The map describes ownership. It does not suggest wrongdoing by anyone named.

## Corrections

If something is wrong or out of date, use “Suggest a correction” on the map. Every suggestion is reviewed by hand before anything changes.

## Sources and licences

- HM Land Registry: Overseas companies that own property in England and Wales; UK companies that own property in England and Wales. Contains HM Land Registry data © Crown copyright and database right 2026. This data is licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
- Companies House: company profiles, persons with significant control, and the Register of Overseas Entities. Contains public sector information licensed under the Open Government Licence v3.0.
- Food Standards Agency: Food Hygiene Rating Scheme data, licensed under the Open Government Licence v3.0.
- postcodes.io: contains OS data © Crown copyright and database right 2026; Royal Mail data © Royal Mail copyright and database right 2026; ONS data licensed under the Open Government Licence v3.0.
- Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors; tiles by [OpenFreeMap](https://openfreemap.org) and [OpenMapTiles](https://www.openmaptiles.org/); built with [Leaflet](https://leafletjs.com) and [MapLibre](https://maplibre.org).

## Inspiration

- [London Food Money Matrix](http://london-food-money-matrix.vercel.app/), the project that prompted this one.
- Key reading: Goulding, Leaver, and Silver, *Manchester Off-Shored: A Public Interest Report on the Manchester Life Partnership*, University of Sheffield, 2022.
