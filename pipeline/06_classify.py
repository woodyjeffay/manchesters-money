"""Step 6: assign ultimate owner, country and owner type.

Inputs: data/interim/chains.jsonl, data/interim/overseas_entities.jsonl
Output: data/interim/classified.csv (one row per starting company / OE proprietor)

Rules first; data/curated/overrides.csv always wins (applied in 08_build.py,
keyed on company_number or title_number).

Never guess: a chain that ends in an offshore entity with no named owner is
'unknown', not assigned a country it might plausibly belong to.
"""
import json
import re

import pandas as pd

from config import INTERIM
from countries import OFFSHORE, to_iso

STATE = re.compile(r"investment authority|sovereign|government of|ministry|public investment fund|"
                   r"state of |emirate|royal court|national fund|holding company of the state|"
                   r"temasek|\bgic\b|mubadala|qatar investment|kuwait investment|norges bank", re.I)
INSTITUTIONAL = re.compile(r"pension|insurance|assurance|asset management|investment management|"
                           r"real estate fund|reit|capital partners|fund\b|kapitalverwaltung|"
                           r"pensionskasse|superannuation", re.I)


def country(j):
    return to_iso(j)


def classify_chain(chain, end_reason):
    if not chain:
        return None, None, "unknown", "empty chain"
    end = chain[-1]
    name = end.get("name") or ""
    if end.get("type") == "individual":
        c = country(end.get("country_of_residence")) or country(end.get("nationality"))
        return name, c, "individual", "PSC individual"
    c = country(end.get("jurisdiction"))
    if STATE.search(name):
        return name, c, "state", "name keyword (state)"
    if c in OFFSHORE and end_reason == "foreign_entity":
        return name, c, "unknown", "chain ends in offshore entity"
    if INSTITUTIONAL.search(name):
        return name, c, "institutional", "name keyword (institutional)"
    if end_reason in ("foreign_entity", "legal_person"):
        return name, c, "corporate", end_reason
    return name, c, "unknown", end_reason


def main():
    rows = []
    path = INTERIM / "chains.jsonl"
    if path.exists():
        for line in path.open():
            r = json.loads(line)
            owner, c, t, why = classify_chain(r["chain"], r["end_reason"])
            rows.append({"key": r["start"], "kind": "company", "ultimate_owner": owner,
                         "ultimate_country": c, "owner_type": t, "rule": why,
                         "chain": json.dumps(r["chain"]), "flags": "|".join(r["flags"])})
    oe = INTERIM / "overseas_entities.jsonl"
    if oe.exists():
        for line in oe.open():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:  # last line may be mid-write while step 5 runs
                continue
            bos = [b for b in r["beneficial_owners"] if not b.get("ceased_on")]
            if not bos:
                rows.append({"key": r["proprietor"], "kind": "proprietor", "owner_type": "unknown",
                             "rule": "no beneficial owner found", "chain": "[]"})
                continue
            head = {"name": r["proprietor"], "company_number": r["oe_number"], "type": "overseas-entity",
                    "source": bos[0]["source"]}
            results = []  # one (owner, country, type, why, chain) per beneficial owner
            for b in bos:
                step = {"name": b["name"], "type": b["kind"], "source": b["source"],
                        "jurisdiction": (b.get("identification") or {}).get("country_registered")
                        or (b.get("identification") or {}).get("place_registered")}
                if "individual" in (b.get("kind") or ""):
                    step.update(type="individual", country_of_residence=b.get("country_of_residence"),
                                nationality=b.get("nationality"))
                    chain = [head, step]
                    res = classify_chain(chain, "individual")
                elif b.get("onward_chain"):
                    chain = [head] + b["onward_chain"]
                    res = classify_chain(chain, b["onward_end"])
                else:
                    chain = [head, step]
                    res = classify_chain(chain, "legal_person" if "legal-person" in (b.get("kind") or "")
                                         else "foreign_entity")
                results.append((*res, chain))
            foreign = [x for x in results if x[1] != "UK"]
            flags = ["multiple_bo"] if len(results) > 1 else []
            if not foreign:
                owner, c, t, why, chain = results[0]
                why = "all beneficial owners UK"
            else:
                owner, c, t, why, chain = foreign[0]
                if len(foreign) < len(results):
                    flags.append("mixed_uk_foreign")
                if len({x[1] for x in foreign}) > 1:
                    flags.append("multiple_foreign_countries")
                    owner = "; ".join(x[0] for x in foreign)
            rows.append({"key": r["proprietor"], "kind": "proprietor", "ultimate_owner": owner,
                         "ultimate_country": c, "owner_type": t, "rule": "ROE: " + why,
                         "chain": json.dumps(chain), "flags": "|".join(flags)})
    df = pd.DataFrame(rows)
    df.to_csv(INTERIM / "classified.csv", index=False)
    if len(df):
        print(df["owner_type"].value_counts().to_string())
        print((df["ultimate_country"].value_counts().head(10)).to_string())


if __name__ == "__main__":
    main()
