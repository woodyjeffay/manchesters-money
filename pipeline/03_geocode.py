"""Step 3: geocode every postcode we know about via postcodes.io (bulk, cached).

Reads postcodes from whatever of these exist:
  data/interim/ocod_manchester.csv, data/interim/ccod_manchester.csv,
  data/interim/fsa_manchester.csv, data/curated/seed.csv
Writes data/interim/postcodes.csv (postcode, lat, lon, ward, terminated)
and logs failures to data/interim/geocode_failures.csv.

Terminated postcodes fall back to their last known location (flagged).
"""
import json
import re

import pandas as pd

from common import SESSION, cached_get_json, normalise_postcode
from config import CACHE, CURATED, INTERIM

SOURCES = [
    (INTERIM / "ocod_manchester.csv", "Postcode"),
    (INTERIM / "ccod_manchester.csv", "Postcode"),
    (INTERIM / "fsa_manchester.csv", "postcode"),
    (CURATED / "seed.csv", "postcode"),
]
BULK_CACHE = CACHE / "postcodes_bulk.json"


def collect():
    pcs = set()
    for path, col in SOURCES:
        if path.exists():
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            if col in df.columns:
                got = {normalise_postcode(p) for p in df[col]}
                got.discard(None)
                print(f"  {path.name}: {len(got):,} postcodes")
                pcs |= got
    return sorted(pcs)


def main():
    pcs = collect()
    cache = json.loads(BULK_CACHE.read_text()) if BULK_CACHE.exists() else {}
    todo = [p for p in pcs if p not in cache]
    print(f"{len(pcs):,} postcodes, {len(todo):,} not yet cached")

    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        r = SESSION.post("https://api.postcodes.io/postcodes",
                         json={"postcodes": batch}, timeout=60)
        r.raise_for_status()
        for item in r.json()["result"]:
            cache[normalise_postcode(item["query"])] = item["result"]
        BULK_CACHE.write_text(json.dumps(cache))

    rows, failures = [], []
    for pc in pcs:
        res = cache.get(pc)
        if res:
            rows.append({"postcode": pc, "lat": res["latitude"], "lon": res["longitude"],
                         "ward": res.get("admin_ward"), "district": res.get("admin_district"),
                         "terminated": False})
            continue
        # Fallback: terminated postcodes keep their last location.
        status, data = cached_get_json(
            f"https://api.postcodes.io/terminated_postcodes/{pc.replace(' ', '')}",
            namespace="postcodes_terminated")
        if status == 200 and data and data.get("result"):
            t = data["result"]
            rows.append({"postcode": pc, "lat": t["latitude"], "lon": t["longitude"],
                         "ward": None, "district": None, "terminated": True})
        else:
            failures.append({"postcode": pc, "reason": "not found"})

    pd.DataFrame(rows).to_csv(INTERIM / "postcodes.csv", index=False)
    pd.DataFrame(failures, columns=["postcode", "reason"]).to_csv(
        INTERIM / "geocode_failures.csv", index=False)
    print(f"Geocoded {len(rows):,}; {len(failures):,} failures "
          f"(see {INTERIM / 'geocode_failures.csv'})")
    geocode_addresses()


# --- Address fallback for register titles with no postcode -----------------
# Uses OpenStreetMap Nominatim (max 1 request/second, cached). Results are
# marked precision="address" or "street" so the map can show them as approximate.

LEADING_NOISE = re.compile(
    r"^(?:(?:basement|level \w+|lower ground|ground floor)[ ,]*)?"
    r"(?:parking spaces?|car parking spaces?|parking|garage|store|storage)[^,]*,\s*"
    r"|^(?:the )?(?:land|site|plot|premises)[^,]*?\b(?:at|of|to|adjoining|known as|lying)\b\s*"
    r"|^(?:the )?(?:north|south|east|west|north-east|north-west|south-east|south-west)\w*\s+side\s+of\s+",
    re.I)


def clean_address(addr):
    a = str(addr).strip()
    for _ in range(3):
        a2 = LEADING_NOISE.sub("", a).strip(" ,")
        if a2 == a:
            break
        a = a2
    a = re.sub(r"\b(\d+)\s+to\s+\d+\s*(\((?:odd|even)\))?", r"\1", a, flags=re.I)
    if not re.search(r"manchester|salford", a, re.I):
        a += ", Manchester"
    return a


def nominatim(q):
    status, data = cached_get_json(
        "https://nominatim.openstreetmap.org/search", namespace="nominatim",
        params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "gb",
                "viewbox": "-2.50,53.55,-2.14,53.34", "bounded": 1},
        min_interval=1.1)
    return data[0] if status == 200 and data else None


def geocode_addresses():
    out = []
    for path in (INTERIM / "ocod_manchester.csv", INTERIM / "ccod_manchester.csv"):
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False,
                         usecols=["Title Number", "Property Address", "Postcode", "District"])
        todo = df[df["Postcode"].str.strip() == ""]
        if path.name.startswith("ccod"):
            # CCOD is huge; only geocode CCOD titles once we know they're foreign-controlled.
            keep = INTERIM / "foreign_titles.csv"
            if not keep.exists():
                continue
            todo = todo[todo["Title Number"].isin(set(pd.read_csv(keep, dtype=str)["title_number"]))]
        print(f"  {path.name}: {len(todo):,} titles without postcode -> address geocoding")
        for r in todo.itertuples():
            q = clean_address(r[2])
            town = (r[4] or "Manchester").strip().title()
            hit = nominatim(q)
            precision = "address"
            if not hit:  # retry with just the street + Manchester
                street = re.sub(r"^[\d\w-]*\d[\w-]*\s+", "", q.split(",")[0]).strip()
                hit = nominatim(f"{street}, {town}") if street else None
                precision = "street"
            out.append({"title_number": r[1], "query": q,
                        "lat": hit["lat"] if hit else None, "lon": hit["lon"] if hit else None,
                        "precision": precision if hit else None})
    df = pd.DataFrame(out, columns=["title_number", "query", "lat", "lon", "precision"])
    df.to_csv(INTERIM / "address_geocodes.csv", index=False)
    print(f"  address geocoding: {df['lat'].notna().sum():,} of {len(df):,} placed")


if __name__ == "__main__":
    main()
