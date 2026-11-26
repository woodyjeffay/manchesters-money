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

from config import CURATED, INTERIM
from countries import OFFSHORE, to_iso

STATE = re.compile(r"investment authority|sovereign|government of|ministry|public investment fund|"
                   r"state of |emirate|royal court|national fund|holding company of the state|"
                   r"temasek|\bgic\b|mubadala|qatar investment|kuwait investment|norges bank", re.I)
INSTITUTIONAL = re.compile(r"pension|insurance|assurance|asset management|investment management|"
                           r"real estate fund|reit|capital partners|fund\b|kapitalverwaltung|"
                           r"pensionskasse|superannuation", re.I)
# Members of ruling families count as 'state' (README: "ruler-linked vehicles").
# Deliberately narrow: formal royal styles or the ruling-family names of Gulf states.
# 'Sheikh' alone is a common honorific and is NOT enough.
RULER = re.compile(r"\b(his|her) (royal )?highness\b|\bH\.?R\.?H\b|"
                   r"\bal[- ]?(nahyan|nahayan|maktoum|thani|saud|sabah|khalifa|qasimi|nuaimi|sharqi|mualla)\b",
                   re.I)
# Listed / public companies publish their shareholders, so a chain that ends at one
# is not opaque even in an offshore jurisdiction.
LISTED = re.compile(r"\bp\.?l\.?c\.?$|public limited company", re.I)


def country(j):
    return to_iso(j)


OWNERSHIP = re.compile(r"ownership-of-shares|voting-rights|right-to-appoint|right-to-share-surplus-assets")


def person_country(p):
    # Where someone lives, never their nationality: the map is about control from
    # outside the UK, not about who is foreign. No stated residence -> not established.
    return country(p.get("country_of_residence"))


def classify_people(chain, end):
    """End of chain is one or more individuals controlling the same company."""
    people = end.get("people") or [end]
    natures = [p.get("natures_of_control") or [] for p in people]
    countries = [person_country(p) for p in people]
    prev = chain[-2] if len(chain) > 1 else {}

    # Trustees ('...-as-trust') or partners of a firm ('...-as-firm') act for others.
    # The beneficiaries are not disclosed, so the real owner is unknown.
    if natures and all(any(n.endswith(("-as-trust", "-as-firm")) for n in ns) for ns in natures):
        if all(c == "UK" for c in countries):
            return "Trust with UK trustees", "UK", "unknown", "trustees (UK)"
        return f"Trust behind {prev.get('name') or 'this company'} (beneficiaries not disclosed)", None, "unknown", "trustees"

    # 'Significant influence or control' with no shares, votes or appointment rights:
    # a controller, not an owner. Name the company, not the person.
    if natures and all(ns and not any(OWNERSHIP.search(n) for n in ns) for ns in natures):
        if all(c == "UK" for c in countries):
            return prev.get("name"), "UK", "unknown", "influence only (UK)"
        return prev.get("name"), None, "unknown", "influence only, no ownership recorded"

    # Joint owners: conservative. Any UK-based owner means we don't call it foreign.
    if "UK" in countries or (None in countries and len(set(countries)) == 1):
        return end.get("name"), "UK" if "UK" in countries else None, "individual", "PSC individual(s), UK involved"
    c = next((x for x in countries if x), None)
    names = end.get("name") or ""
    if RULER.search(names):
        return names, c, "state", "ruling-family member"
    rule = "PSC individual" if len(people) == 1 else "joint PSC individuals"
    if len(set(countries)) > 1:
        rule += "; owners in several countries"
    return names, c, "individual", rule


def classify_chain(chain, end_reason):
    if not chain:
        return None, None, "unknown", "empty chain"
    end = chain[-1]
    name = end.get("name") or ""
    if end.get("type") in ("individual", "individuals"):
        return classify_people(chain, end)
    c = country(end.get("jurisdiction"))
    if STATE.search(name):
        return name, c, "state", "name keyword (state)"
    legal_form = (end.get("legal_form") or "")
    listed = LISTED.search(name.strip()) or re.search(r"public|listed", legal_form, re.I)
    if c in OFFSHORE and end_reason == "foreign_entity" and not listed:
        return name, c, "unknown", "chain ends in offshore entity"
    if INSTITUTIONAL.search(name):
        return name, c, "institutional", "name keyword (institutional)"
    if end_reason in ("foreign_entity", "legal_person"):
        return name, c, "corporate", end_reason
    return name, c, "unknown", end_reason


def load_controllers():
    """data/curated/controllers.csv: a sourced, hand-checked controller for a UK company
    that appears in chains (e.g. a fund manager's holding company, where the register
    names the fund manager's founder as PSC). Applied to any chain passing through it."""
    path = CURATED / "controllers.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    return {r["company_number"]: r for r in df.to_dict("records")}


def person_key(name):
    return re.sub(r"^(mr|mrs|ms|miss|dr|sir)\.? ", "", (name or "").strip().lower())


def apply_controller(row, controllers):
    chain = json.loads(row["chain"])
    hit = next((controllers[s["company_number"]] for s in chain
                if s.get("company_number") in controllers), None)
    if not hit and chain:  # fall back to a named person at the end of the chain
        hit = controllers.get("person:" + person_key(chain[-1].get("name")))
    if not hit:
        return row
    chain.append({"name": hit["ultimate_owner"], "type": "curated-controller",
                  "jurisdiction": hit["ultimate_country"], "note": hit["note"], "source": hit["source"]})
    flags = [f for f in (row.get("flags") or "").split("|") if f] + ["curated_controller"]
    flags += [f for f in hit["flags"].split("|") if f]
    return {**row, "ultimate_owner": hit["ultimate_owner"], "ultimate_country": hit["ultimate_country"],
            "owner_type": hit["owner_type"], "rule": "curated controller (sourced)",
            "chain": json.dumps(chain), "flags": "|".join(dict.fromkeys(flags))}


def main():
    rows = []
    # Merge the single-run file and any shard files; prefer a successful walk over an error.
    walked = {}
    for path in [INTERIM / "chains.jsonl", *sorted(INTERIM.glob("chains.part*.jsonl"))]:
        if not path.exists():
            continue
        for line in path.open():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r["start"] not in walked or walked[r["start"]]["end_reason"] == "error":
                walked[r["start"]] = r
    for r in walked.values():
        if True:
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
                                nationality=b.get("nationality"),
                                natures_of_control=b.get("natures_of_control") or [])
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
                # Name every non-UK beneficial owner, not just the first one listed.
                owner = "; ".join(dict.fromkeys(x[0] for x in foreign if x[0])) or owner
            rows.append({"key": r["proprietor"], "kind": "proprietor", "ultimate_owner": owner,
                         "ultimate_country": c, "owner_type": t, "rule": "ROE: " + why,
                         "chain": json.dumps(chain), "flags": "|".join(flags)})
    controllers = load_controllers()
    rows = [apply_controller(r, controllers) for r in rows]
    df = pd.DataFrame(rows)
    df.to_csv(INTERIM / "classified.csv", index=False)
    if len(df):
        print(df["owner_type"].value_counts().to_string())
        print((df["ultimate_country"].value_counts().head(10)).to_string())


if __name__ == "__main__":
    main()
