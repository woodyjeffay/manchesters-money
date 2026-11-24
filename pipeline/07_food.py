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


SUFFIXES = re.compile(r"\b(limited|ltd|plc|llp|uk|the|restaurant|cafe|bar|group)\b")


def norm(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    return " ".join(SUFFIXES.sub(" ", s).split())


def match_companies(df):
    from dotenv import load_dotenv
    from rapidfuzz import fuzz
    load_dotenv()
    key = (os.environ.get("COMPANIES_HOUSE_API_KEY") or "").strip()
    if not key:
        raise SystemExit("Set COMPANIES_HOUSE_API_KEY in .env to run --match")

    out = []
    for r in df.itertuples():
        _, data = cached_get_json(f"{CH}/search/companies", namespace="ch_search",
                                  params={"q": r.business_name, "items_per_page": 10},
                                  auth=(key, ""), min_interval=0.5)
        best, best_score = None, 0
        for item in (data or {}).get("items", []):
            if item.get("company_status") not in ("active", None):
                continue
            score = fuzz.token_sort_ratio(norm(r.business_name), norm(item["title"]))
            addr_pc = (item.get("address") or {}).get("postal_code", "")
            if r.postcode and addr_pc.replace(" ", "").upper() == str(r.postcode).replace(" ", "").upper():
                score += 15  # registered office at the premises is a strong signal
            if score > best_score:
                best, best_score = item, score
        conf = "high" if best_score >= 100 else "medium" if best_score >= 90 else "low"
        out.append({"fhrs_id": r.fhrs_id,
                    "company_number": best["company_number"] if best else None,
                    "company_name": best["title"] if best else None,
                    "match_score": best_score, "match_confidence": conf if best else None})
    return df.merge(pd.DataFrame(out), on="fhrs_id", how="left")


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


if __name__ == "__main__":
    main()
