"""Step 8: merge registers + curated seed + overrides into site/data/properties.geojson.

Works with whatever exists: today that may be only data/curated/seed.csv.
Keeps only foreign-controlled properties (plus 'unknown'). Every feature must
carry at least one source; rows without a source or coordinates are dropped
and listed in data/interim/build_dropped.csv.
"""
import importlib
import json
import re
from datetime import date

import pandas as pd

from common import find_raw_csv, normalise_postcode
from config import CURATED, INTERIM, SITE_DATA
from countries import to_iso

TODAY = date.today().isoformat()
HMLR_OCOD = "https://use-land-property-data.service.gov.uk/datasets/ocod"
HMLR_CCOD = "https://use-land-property-data.service.gov.uk/datasets/ccod"


def read(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else None


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def tenure(v):
    v = str(v).strip().lower()
    return v if v in ("freehold", "leasehold") else None


def seed_features():
    df = read(CURATED / "seed.csv")
    out = []
    for r in (df.to_dict("records") if df is not None else []):
        out.append({
            "id": r["id"], "name": r["name"], "address": r["address"],
            "postcode": r["postcode"] or None,
            "lat": r["lat"], "lon": r["lon"],
            "property_type": r["property_type"] or "other", "tenure": tenure(r["tenure"]),
            "title_numbers": [t for t in r["title_numbers"].split("|") if t],
            "registered_owner": r["registered_owner"] or None,
            "registered_owner_jurisdiction": r["registered_owner_jurisdiction"] or None,
            "ultimate_owner": r["ultimate_owner"] or None,
            "ultimate_country": r["ultimate_country"] or None,
            "owner_type": r["owner_type"] or "unknown",
            "chain": json.loads(r["chain"]) if r["chain"] else [],
            "evidence": r["evidence"] or "curated",
            "sources": [s for s in r["sources"].split("|") if s],
            "price_paid": num(r["price_paid"]),
            "last_checked": r["last_checked"] or TODAY,
            "review_status": r.get("review_status") or None,
            "notes": r.get("notes") or None,
            "area": r.get("area") or "Manchester",
        })
    return out


PTYPE_RULES = [
    ("ground_rent", re.compile(r"\bair ?space\b|ground rent|rent ?charge|freehold reversion|reversionary", re.I)),
    ("land", re.compile(r"^(?:the )?(?:land|site|plot)\b", re.I)),
    ("parking", re.compile(r"parking|garage|car park|\bstorage\b|\bstore\b|bike store|cycle store", re.I)),
    ("hospitality", re.compile(r"hotel|\binn\b|public house|\bpub\b|restaurant|bar\b", re.I)),
    ("residential", re.compile(r"\bflat\b|apartment|\bhouse\b|cottage|maisonette|student", re.I)),
]


def guess_ptype(addr):
    for t, rx in PTYPE_RULES:
        if rx.search(addr or ""):
            return t
    return "other"


def is_foreign(c):
    """Only map titles whose chain leaves the UK (or ends offshore and opaque)."""
    if not c:
        return False
    chain = json.loads(c["chain"] or "[]")
    left_uk = any(to_iso(s.get("jurisdiction") or s.get("country_of_residence"))
                  not in (None, "UK") for s in chain)
    return left_uk and c.get("ultimate_country") != "UK"


def register_features(postcodes):
    """OCOD (all) + CCOD (only foreign-controlled), enriched with step 6 classification."""
    cls = read(INTERIM / "classified.csv")
    by_key = {r["key"]: r for r in cls.to_dict("records")} if cls is not None else {}
    addr = read(INTERIM / "address_geocodes.csv")
    by_title = {r["title_number"]: r for r in addr.to_dict("records") if r["lat"]} if addr is not None else {}
    out, pending = [], []
    for dataset, path, url in (("ocod", INTERIM / "ocod_manchester.csv", HMLR_OCOD),
                               ("ccod", INTERIM / "ccod_manchester.csv", HMLR_CCOD)):
        df = read(path)
        if df is None:
            continue
        for r in df.to_dict("records"):
            owner = r.get("Proprietor Name (1)", "").strip()
            title = r.get("Title Number")
            number = r.get("Company Registration No. (1)", "").strip().upper()
            number = number.zfill(8) if number.isdigit() else number
            if dataset == "ocod":
                juris = to_iso(r.get("Country Incorporated (1)")) or r.get("Country Incorporated (1)", "").strip()
                c = by_key.get(owner)
                if c is None:
                    pending.append(title)  # step 5 hasn't looked this owner up yet
                    continue
            else:
                juris = "UK"
                c = by_key.get(number)
                if not is_foreign(c):
                    continue
            pc = normalise_postcode(r.get("Postcode"))
            geo, precision = postcodes.get(pc), "postcode"
            if not geo and title in by_title:
                geo, precision = by_title[title], by_title[title]["precision"]
            first = {"name": owner, "jurisdiction": juris, "type": "registered-proprietor", "source": url}
            if number:
                first["company_number"] = number
            chain = [first]
            if c:
                chain += [s for s in json.loads(c["chain"])
                          if (s.get("name") or "").upper() != owner.upper() and s.get("company_number") != number]
            out.append({
                "id": f"{dataset.upper()}-{title}", "name": r.get("Property Address", "").split(",")[0].strip(),
                "address": r.get("Property Address"), "postcode": pc,
                "lat": geo.get("lat") if geo else None, "lon": geo.get("lon") if geo else None,
                "geocode_precision": precision if geo else None,
                "property_type": guess_ptype(r.get("Property Address")),
                "tenure": tenure(r.get("Tenure")), "title_numbers": [title],
                "registered_owner": owner, "registered_owner_jurisdiction": juris,
                "area": (r.get("District") or "").strip().title() or None,
                "ultimate_owner": (c or {}).get("ultimate_owner") or None,
                "ultimate_country": (c or {}).get("ultimate_country") or None,
                "owner_type": (c or {}).get("owner_type") or "unknown",
                "chain": chain, "evidence": "inferred" if len(chain) > 1 else "register",
                "sources": [url] + sorted({s["source"] for s in chain[1:] if s.get("source")}),
                "price_paid": num(r.get("Price Paid")), "last_checked": TODAY,
                "review_status": None, "notes": None,
                "flags": [f for f in ((c or {}).get("flags") or "").split("|") if f],
            })
    if pending:
        print(f"  {len(pending):,} OCOD titles skipped: owner not yet looked up in step 5")
    return out


UNIT_PREFIX = re.compile(
    r"^(?:(?:the )?(?:flat|apartment|apt|unit|suite|room|studio|penthouse|duplex|townhouse|"
    r"(?:car )?parking spaces?|space|bay|garage|store|storage|bike store|cycle store|level|floor|"
    r"basement|lower ground floor|ground floor|first floor|second floor|third floor)"
    r"\b[^,]*,\s*)+", re.I)


def building_label(address):
    """'Flat 12, Cotton Field Wharf, 4 Old Mill St, Manchester (M4 6EN)' -> 'Cotton Field Wharf, 4 Old Mill St'."""
    a = UNIT_PREFIX.sub("", str(address or "")).strip(" ,")
    parts = [p.strip() for p in a.split(",") if p.strip() and "manchester" not in p.lower()]
    return ", ".join(parts[:2]) or str(address or "").split(",")[0]


def group_by_building(feats):
    """One pin per owner per location. Curated entries are never merged."""
    groups, order = {}, []
    for f in feats:
        if f["evidence"] == "curated":
            key = ("curated", f["id"])
        else:
            loc = f["postcode"] or (round(f["_lat"], 4), round(f["_lon"], 4))
            key = (f["registered_owner"], f["ultimate_owner"], f["owner_type"], loc)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(f)

    out = []
    for key in order:
        fs = groups[key]
        if len(fs) == 1:
            f = fs[0]
            f["title_count"] = len(f["title_numbers"])
            out.append(f)
            continue
        fs.sort(key=lambda f: f["title_numbers"][0])
        types = [f["property_type"] for f in fs]
        non_parking = [t for t in types if t != "parking"]
        main_type = max(set(non_parking or types), key=(non_parking or types).count)
        labels = [building_label(f["address"]) for f in fs]
        label = max(set(labels), key=labels.count)
        prices = [f["price_paid"] for f in fs if f["price_paid"]]
        g = dict(fs[0])
        g.update({
            "id": fs[0]["id"],
            "name": label,
            "address": label,
            "property_type": main_type,
            "parking_only": not non_parking,
            "tenure": fs[0]["tenure"] if len({f["tenure"] for f in fs}) == 1 else "mixed",
            "title_numbers": [t for f in fs for t in f["title_numbers"]],
            "title_count": sum(len(f["title_numbers"]) for f in fs),
            "titles": [{"title": f["title_numbers"][0], "address": f["address"], "tenure": f["tenure"],
                        "property_type": f["property_type"], "price_paid": f["price_paid"]} for f in fs],
            "price_paid": sum(prices) if prices else None,
            "price_paid_known": len(prices),
            "geocode_precision": "postcode" if any(f["geocode_precision"] == "postcode" for f in fs)
                                 else fs[0]["geocode_precision"],
            "sources": sorted({s for f in fs for s in f["sources"]}, key=lambda s: (not s.startswith(HMLR_OCOD[:40]), s)),
            "flags": sorted({x for f in fs for x in (f.get("flags") or [])}),
        })
        out.append(g)
    return out


HOUSE = re.compile(r"^\d+[a-z]?\s+[A-Za-z]", re.I)
REVIEW_THRESHOLD = 20  # individuals shown with more titles than this are held for review


def mark_ground_rents(feats):
    """A company holding many FREEHOLDS of single houses is almost certainly a ground-rent
    investor (the homes themselves are sold on long leases). Mark these as inferred."""
    by_owner = {}
    for f in feats:
        if f["evidence"] != "curated" and f["tenure"] == "freehold" and HOUSE.match(f["address"] or "") \
                and f["property_type"] in ("residential", "other"):
            by_owner.setdefault(f["registered_owner"], []).append(f)
    n = 0
    for owner, fs in by_owner.items():
        if len(fs) >= 20:
            for f in fs:
                f["property_type"] = "ground_rent"
                f.setdefault("flags", []).append("inferred_ground_rent")
                n += 1
    print(f"  {n:,} freehold house titles marked as likely ground rents")


def hold_for_review(feats):
    """Named individuals with many titles are usually trustees, nominees or fund principals.
    Hold them back until approved in data/curated/approved_owners.csv."""
    approved_path = CURATED / "approved_owners.csv"
    approved = read(approved_path)
    approved = set(approved["ultimate_owner"]) if approved is not None and len(approved) else set()
    counts = {}
    for f in feats:
        # UK-controlled titles are dropped later anyway, so they need no review.
        if (f["owner_type"] == "individual" and f["property_type"] not in ("parking",)
                and f["ultimate_country"] != "UK"):
            counts[f["ultimate_owner"]] = counts.get(f["ultimate_owner"], 0) + 1
    held = {o for o, n in counts.items() if n > REVIEW_THRESHOLD and o not in approved}
    queue = [{"ultimate_owner": o, "titles": counts[o],
              "example_registered_owner": next(f["registered_owner"] for f in feats if f["ultimate_owner"] == o),
              "example_chain": " -> ".join(s.get("name") or "" for s in
                                           next(f["chain"] for f in feats if f["ultimate_owner"] == o))}
             for o in sorted(held, key=lambda o: -counts[o])]
    pd.DataFrame(queue, columns=["ultimate_owner", "titles", "example_registered_owner", "example_chain"]).to_csv(
        CURATED / "review_queue.csv", index=False)
    if not approved_path.exists():
        pd.DataFrame(columns=["ultimate_owner", "decision", "reviewed_by", "date", "source"]).to_csv(
            approved_path, index=False)
    print(f"  {len(held)} individuals held for review ({sum(counts[o] for o in held):,} titles) "
          f"-> data/curated/review_queue.csv")
    return [f for f in feats if f["ultimate_owner"] not in held or f["owner_type"] != "individual"]


# --- Small owners -----------------------------------------------------------------
# Individuals are named only above a threshold. Below it they appear as
# "Private individual" with their country of residence; the registered company
# (a fact from the Land Registry) is still shown. See methodology.html.
NAME_MIN_TITLES = 5            # titles held in the areas covered
NAME_MIN_PRICE = 5_000_000     # total price paid, where the register records it
NAME_MIN_VENUES = 5            # food and drink businesses run
WHOLE_BUILDING_TYPES = ("hospitality", "other")


def approved_names():
    """Owners named regardless of size: public figures and others approved by hand
    in data/curated/approved_owners.csv."""
    df = read(CURATED / "approved_owners.csv")
    return set(df["ultimate_owner"]) if df is not None and len(df) else set()


def is_whole_building(f):
    """A hotel, pub, office or shop title that is not a flat, unit or parking space."""
    return (f["property_type"] in WHOLE_BUILDING_TYPES
            and not UNIT_PREFIX.match(f.get("address") or "")
            and not re.search(r"\bflat\b|apartment|\bunit\b|\bsuite\b", f.get("address") or "", re.I))


def is_named_by_source(f):
    """Curated entries and curated controllers rest on a published source naming the owner."""
    return f.get("evidence") == "curated" or "curated_controller" in (f.get("flags") or [])


def named_individuals(feats, approved):
    """Which individual owners clear the threshold, judged on all their titles."""
    stats = {}
    for f in feats:
        if f["owner_type"] != "individual" or not f.get("ultimate_owner"):
            continue
        s = stats.setdefault(f["ultimate_owner"], {"titles": 0, "price": 0, "whole": False, "sourced": False})
        s["titles"] += len(f["title_numbers"])
        s["price"] += f.get("price_paid") or 0
        s["whole"] |= is_whole_building(f)
        s["sourced"] |= is_named_by_source(f)
    return {o for o, s in stats.items()
            if o in approved or s["sourced"] or s["whole"]
            or s["titles"] >= NAME_MIN_TITLES or s["price"] >= NAME_MIN_PRICE}


def anonymise(p):
    """Replace a below-threshold individual's name everywhere it appears in a feature."""
    several = ";" in (p.get("ultimate_owner") or "")
    label = "Private individuals" if several else "Private individual"
    p["ultimate_owner"] = label
    p["anonymised"] = True
    chain = []
    for s in p.get("chain") or []:
        if s.get("type") in ("individual", "individuals"):
            s = {"name": label, "type": s["type"], "country_of_residence": s.get("country_of_residence"),
                 "note": "Named in the register. Not shown here because this owner holds little property in the area."}
        chain.append(s)
    p["chain"] = chain
    p["sources"] = sorted({s["source"] for s in chain if s.get("source")} |
                          {s for s in p.get("sources") or [] if "use-land-property-data" in s or "ratings.food.gov.uk" in s})
    return p


def protect_small_owners(feats, counter=None):
    """feats: property dicts (before grouping). Anonymises individuals below the threshold."""
    keep = named_individuals(feats, approved_names())
    n, owners = 0, set()
    for f in feats:
        if f["owner_type"] == "individual" and f.get("ultimate_owner") and f["ultimate_owner"] not in keep:
            owners.add(f["ultimate_owner"])
            anonymise(f)
            n += 1
    print(f"  {len(owners):,} individuals below the naming threshold shown as 'Private individual' ({n:,} titles)")
    return feats


def apply_overrides(feats):
    ov = read(CURATED / "overrides.csv")
    if ov is None or ov.empty:
        return feats
    for o in ov.to_dict("records"):
        for f in feats:
            if o["property_id"] == f["id"] or (o["title_number"] and o["title_number"] in f["title_numbers"]):
                f[o["field"]] = json.loads(o["value"]) if o["field"] in ("chain", "sources") else o["value"]
                if o["source"]:
                    f["sources"].append(o["source"])
    return feats


def main():
    pcs = read(INTERIM / "postcodes.csv")
    postcodes = {r["postcode"]: r for r in pcs.to_dict("records")} if pcs is not None else {}
    feats = apply_overrides(seed_features() + register_features(postcodes))
    # Step 3 only address-geocodes CCOD titles on this list (CCOD is too big to geocode whole).
    pd.DataFrame({"title_number": sorted({t for f in feats for t in f["title_numbers"]})}).to_csv(
        INTERIM / "foreign_titles.csv", index=False)
    mark_ground_rents(feats)
    feats = hold_for_review(feats)

    candidates, dropped = [], []
    for f in feats:
        lat, lon = f.pop("lat"), f.pop("lon")
        if (not lat or not lon) and f["postcode"] in postcodes:
            lat, lon = postcodes[f["postcode"]]["lat"], postcodes[f["postcode"]]["lon"]
        reason = ("no source" if not f["sources"] else
                  "no coordinates" if not lat or not lon else
                  "UK-controlled" if f["ultimate_country"] == "UK" else None)
        if reason:
            dropped.append({"id": f["id"], "name": f["name"], "reason": reason})
            continue
        f["_lat"], f["_lon"] = float(lat), float(lon)
        candidates.append(f)

    candidates = protect_small_owners(candidates)
    grouped = group_by_building(candidates)
    kept = []
    for f in grouped:
        lat, lon = f.pop("_lat"), f.pop("_lon")
        kept.append({"type": "Feature",
                     "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                     "properties": f})
    print(f"  {len(candidates):,} titles grouped into {len(kept):,} pins")

    dest = SITE_DATA / "properties.geojson"
    dest.write_text(json.dumps({"type": "FeatureCollection", "generated": TODAY, "meta": release_meta(),
                                "features": kept}, indent=1))
    build_venues(postcodes)
    pd.DataFrame(dropped, columns=["id", "name", "reason"]).to_csv(INTERIM / "build_dropped.csv", index=False)
    print(f"{len(kept)} features -> {dest}; {len(dropped)} dropped (see {INTERIM / 'build_dropped.csv'})")
    for d in dropped[:20]:
        print(f"  dropped {d['id']} {d['name']}: {d['reason']}")


def release_meta():
    """Which register releases the map was built from, for the 'data updated' line."""
    meta = {"built": TODAY}
    for prefix in ("OCOD", "CCOD"):
        try:
            m = re.search(r"(\d{4})_(\d{2})", find_raw_csv(prefix).name)
            meta[prefix.lower()] = f"{m.group(1)}-{m.group(2)}" if m else None
        except SystemExit:
            meta[prefix.lower()] = None
    return meta


FSA_TYPES = {"Restaurant/Cafe/Canteen": "Restaurant or café", "Takeaway/sandwich shop": "Takeaway",
             "Pub/bar/nightclub": "Pub, bar or club", "Hotel/bed & breakfast/guest house": "Hotel",
             "Retailers - supermarkets/hypermarkets": "Supermarket"}


def build_venues(postcodes):
    """Food & drink businesses whose operator (matched by exact name in step 7) is
    controlled from outside the UK -> site/data/venues.geojson."""
    m, chains_path = read(INTERIM / "fsa_matches.csv"), INTERIM / "fsa_chains.jsonl"
    if m is None or not chains_path.exists():
        print("  no food matches yet (run 07_food.py --match)")
        return
    classify = importlib.import_module("06_classify")
    controllers = classify.load_controllers()
    by_num = {}
    for line in chains_path.open():
        r = json.loads(line)
        owner, c, t, why = classify.classify_chain(r["chain"], r["end_reason"])
        row = {"ultimate_owner": owner, "ultimate_country": c, "owner_type": t, "rule": why,
               "chain": json.dumps(r["chain"]), "flags": "|".join(r["flags"])}
        by_num[r["start"]] = classify.apply_controller(row, controllers)
    m = m[m["company_number"].astype(str).str.len() > 0]
    branches = m["company_number"].value_counts()
    feats = []
    for r in m.to_dict("records"):
        c = by_num.get(r["company_number"])
        if not is_foreign(c):
            continue
        lat, lon = r.get("lat"), r.get("lon")
        pc = normalise_postcode(r.get("postcode"))
        if (not lat or not lon) and pc in postcodes:
            lat, lon = postcodes[pc]["lat"], postcodes[pc]["lon"]
        if not lat or not lon:
            continue
        flags = [f for f in (c.get("flags") or "").split("|") if f]
        flags.append("venue_office_match" if r["match_confidence"] == "high" else "venue_name_match")
        if branches[r["company_number"]] >= 3:
            flags.append("venue_brand")
        first = {"name": r["company_name"], "company_number": r["company_number"], "type": "operator",
                 "jurisdiction": "UK", "source": "https://find-and-update.company-information.service.gov.uk/company/"
                 + r["company_number"]}
        chain = [first] + [s for s in json.loads(c["chain"]) if s.get("company_number") != r["company_number"]]
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(float(lon), 6), round(float(lat), 6)]},
                      "properties": {
                          "id": f"FSA-{r['fhrs_id']}", "name": r["business_name"],
                          "business_type": FSA_TYPES.get(r["business_type"], r["business_type"]),
                          "address": r.get("address"), "postcode": pc, "area": r.get("authority"),
                          "rating": r.get("rating"), "rating_date": (r.get("rating_date") or "")[:10] or None,
                          "operator": r["company_name"], "operator_number": r["company_number"],
                          "match_confidence": r["match_confidence"],
                          "ultimate_owner": c["ultimate_owner"], "ultimate_country": c["ultimate_country"],
                          "owner_type": c["owner_type"], "chain": chain, "flags": flags,
                          "sources": [r["source"]] + sorted({s["source"] for s in chain if s.get("source")}),
                      }})
    approved = approved_names()
    venue_counts = {}
    for f in feats:
        p = f["properties"]
        if p["owner_type"] == "individual":
            venue_counts[p["ultimate_owner"]] = venue_counts.get(p["ultimate_owner"], 0) + 1
    for f in feats:
        p = f["properties"]
        if (p["owner_type"] == "individual" and p["ultimate_owner"] not in approved
                and not is_named_by_source(p) and venue_counts.get(p["ultimate_owner"], 0) < NAME_MIN_VENUES):
            anonymise(p)
    dest = SITE_DATA / "venues.geojson"
    dest.write_text(json.dumps({"type": "FeatureCollection", "generated": TODAY, "features": feats}, indent=1))
    print(f"  {len(feats):,} food & drink businesses with a non-UK controller -> {dest}")


if __name__ == "__main__":
    main()
