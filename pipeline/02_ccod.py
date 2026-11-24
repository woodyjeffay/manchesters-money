"""Step 2: load CCOD (UK companies that own property) and filter to the area.

Put CCOD_FULL_YYYY_MM.csv in data/raw/ then run:

    python pipeline/02_ccod.py --inspect
    python pipeline/02_ccod.py

Outputs data/interim/ccod_manchester.csv and data/interim/ccod_company_numbers.csv
(the distinct company numbers that step 4 will walk).
"""
import argparse
import pandas as pd

from common import find_raw_csv
from config import AREAS, INTERIM

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true")
    args = ap.parse_args()

    path = find_raw_csv("CCOD")
    print(f"Reading {path.name} in chunks (large file)")
    areas = {a.upper() for a in AREAS}
    parts, total = [], 0
    for chunk in pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8",
                             encoding_errors="replace", chunksize=250_000):
        total += len(chunk)
        if args.inspect:
            hits = chunk["District"].str.strip()
            parts.append(hits[hits.str.upper().str.contains("MANCHESTER", na=False)])
            continue
        parts.append(chunk[chunk["District"].str.strip().str.upper().isin(areas)])
    print(f"CCOD: {total:,} rows; columns: {list(chunk.columns)}")
    if args.inspect:
        print(pd.concat(parts).value_counts().to_string())
        return

    out = pd.concat(parts)
    out.insert(0, "source_file", path.name)
    out.to_csv(INTERIM / "ccod_manchester.csv", index=False)
    print(f"\nKept {len(out):,} titles -> {INTERIM / 'ccod_manchester.csv'}")

    num_cols = [c for c in out.columns if c.startswith("Company Registration No")]
    nums = pd.Series(pd.concat([out[c] for c in num_cols]).str.strip().str.upper())
    nums = nums[nums != ""].drop_duplicates().sort_values()
    # Companies House numbers are 8 chars, zero-padded when purely numeric.
    nums = nums.map(lambda n: n.zfill(8) if n.isdigit() else n)
    nums.to_frame("company_number").to_csv(INTERIM / "ccod_company_numbers.csv", index=False)
    print(f"{len(nums):,} distinct company numbers -> {INTERIM / 'ccod_company_numbers.csv'}")


if __name__ == "__main__":
    main()
