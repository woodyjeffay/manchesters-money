"""Shared configuration for the pipeline.

To expand beyond Manchester, add districts to AREAS and FSA authority names
to FSA_AUTHORITIES. Land Registry district spellings must be confirmed by
running 01_ocod.py first (it prints the distinct values).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
CACHE = DATA / "cache"
INTERIM = DATA / "interim"
CURATED = DATA / "curated"
SITE_DATA = ROOT / "site" / "data"

# Land Registry "District" values to keep. Confirm against 01_ocod.py output
# before relying on this. Greater Manchester later: add "SALFORD", "TRAFFORD", ...
AREAS = ["MANCHESTER"]

# FSA local authority names (see https://api.ratings.food.gov.uk/Authorities/basic)
FSA_AUTHORITIES = ["Manchester"]

# Manchester City Council postcode districts, used as a sanity check only.
MANCHESTER_POSTCODE_PREFIXES = (
    "M1 ", "M2 ", "M3 ", "M4 ", "M8 ", "M9 ", "M11", "M12", "M13", "M14",
    "M15", "M16", "M18", "M19", "M20", "M21", "M22", "M23", "M40", "M90",
)

for d in (RAW, CACHE, INTERIM, CURATED, SITE_DATA):
    d.mkdir(parents=True, exist_ok=True)
