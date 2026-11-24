"""Step 7 (phase 3): food businesses from the FSA Food Hygiene Rating API.

    python pipeline/07_food.py           # fetch establishments -> data/interim/fsa_manchester.csv
    python pipeline/07_food.py --match   # also fuzzy-match to Companies House (needs API key)

Matching is deliberately conservative: a match is only a candidate for step 4
chain-walking. Confidence is recorded so the map can show or hide weak matches.
"""
import argparse
import os
import re

import pandas as pd

from common import cached_get_json
from config import FSA_AUTHORITIES, INTERIM

FSA = "https://api.ratings.food.gov.uk"
FSA_HEADERS = {"x-api-version": "2", "accept": "application/json"}
CH = "https://api.company-information.service.gov.uk"


def authority_ids():
    _, data = cached_get_json(f"{FSA}/Authorities/basic", namespace="fsa",
                              headers=FSA_HEADERS, max_age_days=30)
    ids = {a["Name"]: a["LocalAuthorityId"] for a in data["authorities"]}
    return {name: ids[name] for name in FSA_AUTHORITIES}


def fetch_establishments():
    rows = []
    for name, la_id in authority_ids().items():
        page = 1
        while True:
            _, data = cached_get_json(
                f"{FSA}/Establishments", namespace="fsa", headers=FSA_HEADERS,
                params={"localAuthorityId": la_id, "pageSize": 5000, "pageNumber": page},
                max_age_days=30)
            for e in data["establishments"]:
                geo = e.get("geocode") or {}
                rows.append({
                    "fhrs_id": e["FHRSID"],
                    "business_name": e["BusinessName"],
                    "business_type": e["BusinessType"],
                    "address": ", ".join(filter(None, (e.get(f"AddressLine{i}") for i in range(1, 5)))),
                    "postcode": e.get("PostCode"),
                    "lat": geo.get("latitude"),
                    "lon": geo.get("longitude"),
                    "rating": e.get("RatingValue"),
                    "rating_date": e.get("RatingDate"),
                    "authority": name,
                    "source": f"https://ratings.food.gov.uk/business/{e['FHRSID']}",
                })
            meta = data["meta"]
            if page >= meta["totalPages"]:
                break
            page += 1
    return pd.DataFrame(rows)


# Only places people eat, drink, stay or shop for food. Schools, care homes, mobile
# caterers and wholesalers are left out.
VENUE_TYPES = ["Restaurant/Cafe/Canteen", "Takeaway/sandwich shop", "Pub/bar/nightclub",
               "Hotel/bed & breakfast/guest house", "Retailers - supermarkets/hypermarkets"]
SUFFIXES = re.compile(r"\b(limited|ltd|plc|llp|the|co|company)\b")


def norm(s):
    s = re.sub(r"[^a-z0-9 ]", "", str(s).lower().replace("&", " and "))
    return " ".join(SUFFIXES.sub(" ", s).split())


def keys():
    from dotenv import load_dotenv
    load_dotenv()
    ks = [k for k in ((os.environ.get(v) or "").strip() for v in
          ("COMPANIES_HOUSE_API_KEY", "COMPANIES_HOUSE_API_KEY_2", "COMPANIES_HOUSE_API_KEY_3")) if k]
    if not ks:
        raise SystemExit("Set COMPANIES_HOUSE_API_KEY in .env to run --match")
    return ks


def best_match(name, postcodes, key):
    """Never guess: the company name must equal the trading name once 'Ltd' etc. are
    removed. 'high' = its registered office is also at one of the venue postcodes;
    'name_only' = an exact name match and the only active company with that name."""
    _, data = cached_get_json(f"{CH}/search/companies", namespace="ch_search",
                              params={"q": name, "items_per_page": 20},
                              auth=(key, ""), min_interval=0.55)
    exact = [i for i in (data or {}).get("items", [])
             if i.get("company_status") == "active" and norm(i.get("title")) == norm(name)]
    for i in exact:
        pc = ((i.get("address") or {}).get("postal_code") or "").replace(" ", "").upper()
        if pc and pc in postcodes:
            return i, "high"
    if len(exact) == 1:
        return exact[0], "name_only"
    return None, None


def match_companies(df):
    from concurrent.futures import ThreadPoolExecutor
    ks = keys()
    venues = df[df["business_type"].isin(VENUE_TYPES)].copy()
    venues["n"] = venues["business_name"].map(norm)
    groups = {n: set(g["postcode"].dropna().str.replace(" ", "").str.upper())
              for n, g in venues.groupby("n") if n}
    names = sorted(groups)
    first_name = venues.groupby("n")["business_name"].first()

    def run(shard):
        out = []
        for j, n in enumerate(names[shard::len(ks)], 1):
            item, conf = best_match(first_name[n], groups[n], ks[shard])
            if item:
                out.append({"n": n, "company_number": item["company_number"],
                            "company_name": item["title"], "match_confidence": conf})
            if j % 250 == 0:
                print(f"  key {shard + 1}: {j:,} names searched", flush=True)
        return out

    with ThreadPoolExecutor(len(ks)) as ex:
        found = [r for part in ex.map(run, range(len(ks))) for r in part]
    m = pd.DataFrame(found, columns=["n", "company_number", "company_name", "match_confidence"])
    print(f"{len(names):,} venue names searched; {len(m):,} matched "
          f"({(m['match_confidence'] == 'high').sum():,} with registered office at the venue)")
    return venues.merge(m, on="n", how="left").drop(columns="n")


def walk_matches(m):
    """Walk the PSC chain of every matched company -> data/interim/fsa_chains.jsonl."""
    import importlib
    import json
    from concurrent.futures import ThreadPoolExecutor
    chains = importlib.import_module("04_chains")
    ks = keys()
    nums = sorted(set(m["company_number"].dropna()))

    def run(shard):
        chains._local.key = ks[shard]
        out = []
        for n in nums[shard::len(ks)]:
            try:
                chain, reason, flags = chains.walk(n)
            except Exception as e:
                chain, reason, flags = [], "error", [repr(e)]
            out.append({"start": n, "chain": chain, "end_reason": reason, "flags": flags})
        return out

    with ThreadPoolExecutor(len(ks)) as ex:
        rows = [r for part in ex.map(run, range(len(ks))) for r in part]
    with open(INTERIM / "fsa_chains.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"{len(rows):,} matched companies walked -> fsa_chains.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", action="store_true")
    args = ap.parse_args()

    df = fetch_establishments()
    dest = INTERIM / "fsa_manchester.csv"
    df.to_csv(dest, index=False)
    print(f"{len(df):,} establishments -> {dest}")
    print(df["business_type"].value_counts().to_string())

    if args.match:
        m = match_companies(df)
        m.to_csv(INTERIM / "fsa_matches.csv", index=False)
        print(m["match_confidence"].value_counts(dropna=False).to_string())
        walk_matches(m)


if __name__ == "__main__":
    main()
