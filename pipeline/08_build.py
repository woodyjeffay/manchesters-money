"""Step 8: merge registers + curated seed + overrides into site/data/properties.geojson.

Works with whatever exists: today that may be only data/curated/seed.csv.
Keeps only foreign-controlled properties (plus 'unknown'). Every feature must
carry at least one source; rows without a source or coordinates are dropped
and listed in data/interim/build_dropped.csv.
"""
import json
import re
from datetime import date

import pandas as pd

from common import normalise_postcode
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
        })
    return out


PTYPE_RULES = [
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
    left_uk = any(to_iso(s.get("jurisdiction") or s.get("country_of_residence") or s.get("nationality"))
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

    grouped = group_by_building(candidates)
    kept = []
    for f in grouped:
        lat, lon = f.pop("_lat"), f.pop("_lon")
        kept.append({"type": "Feature",
                     "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                     "properties": f})
    print(f"  {len(candidates):,} titles grouped into {len(kept):,} pins")

    dest = SITE_DATA / "properties.geojson"
    dest.write_text(json.dumps({"type": "FeatureCollection", "generated": TODAY, "features": kept}, indent=1))
    pd.DataFrame(dropped, columns=["id", "name", "reason"]).to_csv(INTERIM / "build_dropped.csv", index=False)
    print(f"{len(kept)} features -> {dest}; {len(dropped)} dropped (see {INTERIM / 'build_dropped.csv'})")
    for d in dropped[:20]:
        print(f"  dropped {d['id']} {d['name']}: {d['reason']}")


if __name__ == "__main__":
    main()
