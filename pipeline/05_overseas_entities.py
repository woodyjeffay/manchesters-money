"""Step 5: Register of Overseas Entities beneficial owners for OCOD proprietors.

Overseas entities that hold UK land have an OE number (e.g. OE001234) at
Companies House. Their registrable beneficial owners are exposed through the
same PSC endpoint as UK companies. We find the OE number by searching the
proprietor name, accepting only exact (normalised) name matches.

Writes data/interim/overseas_entities.jsonl.
TODO once API key is in place: confirm what the PSC endpoint returns for OEs
(kinds like 'registered-overseas-entity-beneficial-owner...').
"""
import importlib
import json
import os
import re
import unicodedata

import pandas as pd
from dotenv import load_dotenv

from common import cached_get_json
from config import INTERIM

chains = importlib.import_module("04_chains")

load_dotenv()
KEY = (os.environ.get("COMPANIES_HOUSE_API_KEY") or "").strip()
API = "https://api.company-information.service.gov.uk"
WEB = "https://find-and-update.company-information.service.gov.uk/company/"


def norm(s):
    """Compare names ignoring accents, punctuation and LIMITED/LTD (e.g. 'S.A.R.L.' == 'S.À R.L')."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", s.upper().replace("LIMITED", "LTD"))


def ch(path, params=None):
    return cached_get_json(API + path, namespace="ch", params=params, auth=(KEY, ""), min_interval=0.55)


def find_oe(name):
    _, data = ch("/search/companies", {"q": name, "items_per_page": 20})
    for item in (data or {}).get("items", []):
        num = item.get("company_number", "")
        if num.startswith("OE") and norm(item.get("title")) == norm(name):
            return num
    return None


def find_uk_company(name):
    """Exact-name match to a live UK-registered company (not an OE), else None."""
    if not name:
        return None
    _, data = ch("/search/companies", {"q": name, "items_per_page": 10})
    for item in (data or {}).get("items", []):
        num = item.get("company_number", "")
        if not num.startswith("OE") and norm(item.get("title")) == norm(name):
            return num
    return None


def main():
    if not KEY:
        raise SystemExit("Set COMPANIES_HOUSE_API_KEY in .env")
    df = pd.read_csv(INTERIM / "ocod_manchester.csv", dtype=str, keep_default_na=False)
    name_cols = [c for c in df.columns if c.startswith("Proprietor Name")]
    names = sorted({n.strip() for c in name_cols for n in df[c] if n.strip()})
    print(f"{len(names):,} distinct overseas proprietors")
    done = 0
    with open(INTERIM / "overseas_entities.jsonl", "w") as f:
        for name in names:
            oe = find_oe(name)
            rec = {"proprietor": name, "oe_number": oe, "beneficial_owners": []}
            if oe:
                _, pscs = ch(f"/company/{oe}/persons-with-significant-control")
                for p in (pscs or {}).get("items", []):
                    bo = {
                        "name": p.get("name"), "kind": p.get("kind"),
                        "nationality": p.get("nationality"),
                        "country_of_residence": p.get("country_of_residence"),
                        "identification": p.get("identification"),
                        "natures_of_control": p.get("natures_of_control"),
                        "ceased_on": p.get("ceased_on"),
                        "source": WEB + oe + "/persons-with-significant-control"}
                    # A corporate beneficial owner registered in the UK: keep walking its PSC chain.
                    if "corporate" in (p.get("kind") or "") and not p.get("ceased_on"):
                        num = chains.uk_number_from_psc(p) or find_uk_company(p.get("name"))
                        if num:
                            onward, reason, flags = chains.walk(num)
                            bo["uk_company_number"] = num
                            bo["onward_chain"], bo["onward_end"], bo["onward_flags"] = onward, reason, flags
                    rec["beneficial_owners"].append(bo)
            f.write(json.dumps(rec) + "\n")
            done += 1
            if done % 50 == 0:
                print(f"  {done:,}/{len(names):,}", flush=True)


if __name__ == "__main__":
    main()
