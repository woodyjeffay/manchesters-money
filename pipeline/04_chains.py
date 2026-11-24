"""Step 4: walk PSC chains on Companies House for every company number.

Reads company numbers from data/interim/ccod_company_numbers.csv (and, if
present, data/interim/fsa_matches.csv high/medium matches).
Writes data/interim/chains.jsonl: one JSON object per starting company:
  {"start": "01234567", "chain": [...steps...], "end_reason": "...", "flags": [...]}

Stop conditions: an individual PSC, a state/government PSC, a foreign entity
with no UK registration, no PSC data, a cycle, or MAX_HOPS.
All API responses are cached in data/cache/ch/.
"""
import json
import os
import re

import pandas as pd
from dotenv import load_dotenv

from common import cached_get_json
from config import INTERIM
from countries import to_iso

load_dotenv()
# Up to three keys (one per Companies House application) so the walk can run as
# parallel shards: python pipeline/04_chains.py --shard 0 --of 3, etc.
KEYS = [k for k in ((os.environ.get(v) or "").strip() for v in
        ("COMPANIES_HOUSE_API_KEY", "COMPANIES_HOUSE_API_KEY_2", "COMPANIES_HOUSE_API_KEY_3")) if k]
KEY = KEYS[0] if KEYS else ""
API = "https://api.company-information.service.gov.uk"
WEB = "https://find-and-update.company-information.service.gov.uk/company/"
MAX_HOPS = 8
# 600 requests / 5 min = 2/s. Stay a little under.
MIN_INTERVAL = 0.55


def ch(path):
    return cached_get_json(API + path, namespace="ch", auth=(KEY, ""), min_interval=MIN_INTERVAL)


UK_REGISTERS = re.compile(r"companies house|registrar of companies|england|wales|scotland|united kingdom", re.I)


def uk_number_from_psc(psc):
    """A corporate PSC registered at Companies House gives us its number to follow."""
    ident = psc.get("identification") or {}
    reg = ident.get("registration_number")
    place = " ".join(filter(None, [ident.get("place_registered"), ident.get("country_registered"),
                                   ident.get("legal_authority")]))
    if reg and to_iso(place) == "UK":
        reg = reg.strip().upper().replace(" ", "")
        return reg.zfill(8) if reg.isdigit() else reg
    return None


def step_for_company(number, profile):
    return {"name": profile.get("company_name") if profile else None, "company_number": number,
            "jurisdiction": "UK" if profile and profile.get("jurisdiction") in
            ("england-wales", "scotland", "northern-ireland", "united-kingdom", "wales") else
            (profile or {}).get("jurisdiction"),
            "type": "company", "source": WEB + number}


def walk(start):
    chain, seen, flags = [], set(), []
    number = start
    for hop in range(MAX_HOPS):
        if number in seen:
            flags.append("cycle")
            return chain, "cycle", flags
        seen.add(number)
        status, profile = ch(f"/company/{number}")
        if status != 200:
            chain.append({"company_number": number, "source": WEB + number, "type": "company"})
            return chain, f"profile_{status}", flags
        chain.append(step_for_company(number, profile))
        status, pscs = ch(f"/company/{number}/persons-with-significant-control")
        items = [p for p in (pscs or {}).get("items", []) if not p.get("ceased_on")]
        if not items:
            return chain, "no_psc", flags
        if len(items) > 1:
            flags.append(f"multiple_psc@{number}")

        # Follow the controlling legal entity if there is one; otherwise record the end.
        corporates = [p for p in items if "corporate-entity" in p.get("kind", "")
                      or "legal-person" in p.get("kind", "")]
        individuals = [p for p in items if "individual" in p.get("kind", "")]
        if individuals and not corporates:
            # Joint controllers are ONE step (they control the same company side by side),
            # not a sequence. How they hold control matters: '...-as-trust' means a trustee,
            # 'significant-influence-or-control' alone means no shares or votes.
            people = [{"name": p.get("name"), "nationality": p.get("nationality"),
                       "country_of_residence": p.get("country_of_residence"),
                       "natures_of_control": p.get("natures_of_control") or []} for p in individuals]
            step = {"type": "individual" if len(people) == 1 else "individuals",
                    "name": "; ".join(p["name"] or "" for p in people),
                    "people": people,
                    "source": WEB + number + "/persons-with-significant-control"}
            if len(people) == 1:
                step.update({k: people[0][k] for k in ("nationality", "country_of_residence", "natures_of_control")})
            chain.append(step)
            return chain, "individual", flags
        if not corporates:
            # e.g. 'super-secure' PSCs whose details are suppressed for safety reasons.
            chain.append({"name": "Controller details not disclosed", "type": "other",
                          "kinds": sorted({p.get("kind", "") for p in items}),
                          "source": WEB + number + "/persons-with-significant-control"})
            return chain, "undisclosed_psc", flags
        # Pick the corporate PSC with the strongest control (75-100% first).
        corporates.sort(key=lambda p: -max((int(m) for n in p.get("natures_of_control", [])
                                             for m in re.findall(r"(\d+)-to-100", n)), default=0))
        top = corporates[0]
        ident = top.get("identification") or {}
        step = {"name": top.get("name"), "type": "legal-person" if "legal-person" in top["kind"] else "corporate",
                "jurisdiction": ident.get("country_registered") or ident.get("place_registered"),
                "legal_form": ident.get("legal_form"), "registration_number": ident.get("registration_number"),
                "natures_of_control": top.get("natures_of_control"),
                "source": WEB + number + "/persons-with-significant-control"}
        if "legal-person" in top["kind"]:
            chain.append(step)
            return chain, "legal_person", flags  # often a state or government body
        nxt = uk_number_from_psc(top)
        if not nxt:
            chain.append(step)
            return chain, "foreign_entity", flags
        number = nxt
    flags.append("max_hops")
    return chain, "max_hops", flags


def main():
    global KEY
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0, help="which shard this process walks (0-based)")
    ap.add_argument("--of", type=int, default=1, help="total number of shards")
    args = ap.parse_args()
    if not KEYS:
        raise SystemExit("Set COMPANIES_HOUSE_API_KEY in .env")
    KEY = KEYS[args.shard % len(KEYS)]

    nums = set(pd.read_csv(INTERIM / "ccod_company_numbers.csv", dtype=str)["company_number"])
    fsa = INTERIM / "fsa_matches.csv"
    if fsa.exists():
        m = pd.read_csv(fsa, dtype=str)
        nums |= set(m[m["match_confidence"].isin(["high", "medium"])]["company_number"].dropna())
    mine = [n for i, n in enumerate(sorted(nums)) if i % args.of == args.shard]
    out = INTERIM / ("chains.jsonl" if args.of == 1 else f"chains.part{args.shard}of{args.of}.jsonl")
    print(f"Shard {args.shard + 1}/{args.of}: walking {len(mine):,} of {len(nums):,} companies -> {out.name}",
          flush=True)
    with open(out, "w", buffering=1) as f:
        for i, n in enumerate(mine, 1):
            try:
                chain, reason, flags = walk(n)
            except Exception as e:  # record and continue; never crash the batch
                chain, reason, flags = [], "error", [repr(e)]
            f.write(json.dumps({"start": n, "chain": chain, "end_reason": reason, "flags": flags}) + "\n")
            if i % 100 == 0:
                print(f"  {i:,}/{len(mine):,}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
