"""Step 1: load OCOD (overseas companies that own property) and filter to the area.

Put the monthly OCOD_FULL_YYYY_MM.csv in data/raw/ then run:

    python pipeline/01_ocod.py --inspect   # print columns + candidate districts
    python pipeline/01_ocod.py             # write data/interim/ocod_manchester.csv

The filter in config.AREAS must be agreed after looking at --inspect output.
"""
import argparse

import pandas as pd

from common import find_raw_csv
from config import AREAS, INTERIM


def load(path):
    # Land Registry CSVs are UTF-8 but occasionally contain stray bytes.
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8",
                       encoding_errors="replace", low_memory=False)


def inspect(df, label):
    print(f"\n{label}: {len(df):,} rows")
    print("\nColumns:")
    for c in df.columns:
        print(f"  - {c}")
    for col in ("District", "County", "Region"):
        if col not in df.columns:
            print(f"\n(no '{col}' column)")
            continue
        vals = df[col].str.strip()
        hits = vals[vals.str.upper().str.contains("MANCHESTER", na=False)]
        print(f"\nDistinct {col} values containing 'MANCHESTER':")
        for v, n in hits.value_counts().items():
            print(f"  {v!r}: {n:,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true",
                    help="print columns and candidate district values, then stop")
    args = ap.parse_args()

    path = find_raw_csv("OCOD")
    print(f"Reading {path.name}")
    df = load(path)
    inspect(df, "OCOD")
    if args.inspect:
        return

    if "District" not in df.columns:
        raise SystemExit("No District column; check the column list above and update this script.")
    mask = df["District"].str.strip().str.upper().isin([a.upper() for a in AREAS])
    out = df[mask].copy()
    out.insert(0, "source_file", path.name)
    dest = INTERIM / "ocod_manchester.csv"
    out.to_csv(dest, index=False)
    print(f"\nKept {len(out):,} titles where District in {AREAS} -> {dest}")
    country_cols = [c for c in out.columns if c.startswith("Country Incorporated")]
    if country_cols:
        print("\nTop countries of incorporation (first proprietor):")
        print(out[country_cols[0]].value_counts().head(15).to_string())


if __name__ == "__main__":
    main()
