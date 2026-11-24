"""Normalise the free-text countries, registries and nationalities found in
Land Registry and Companies House data to ISO 3166-1 alpha-2 codes.

UK is kept as "UK" (the project's convention). "XC" is used for the bare
value "CHANNEL ISLANDS", which could be Jersey or Guernsey.
Unrecognised values return None and are listed by `python pipeline/countries.py`.
"""
import re

# Ordered: first match wins, so specific patterns (Gibraltar's "Companies House",
# "British Virgin Islands") come before generic ones ("Companies House", "British").
RULES = [
    ("GI", r"GIBRALTAR"),
    ("VG", r"BRITISH VIRGIN|VIRGIN ISLANDS, BRITISH|\bBVI\b"),
    ("UK", r"COMPANIES HOUSE|REGISTRAR OF COMPANIES.*(ENGLAND|UNITED KINGDOM)|UK REGISTER|"
           r"\bUNITED KINGDOM\b|^UK$|ENGLAND|WALES|SCOTLAND|NORTHERN IRELAND|^BRITISH|ENGLISH|\bFCA\b"),
    ("JE", r"JERSEY"),
    ("GG", r"GUERNSEY|GURENSEY|ALDERNEY"),
    ("XC", r"^CHANNEL ISLANDS$"),
    ("IM", r"ISLE OF MAN|MANX"),
    ("KY", r"CAYMAN"),
    ("BM", r"BERMUDA"),
    ("BS", r"BAHAMAS"),
    ("TC", r"TURKS AND CAICOS"),
    ("AI", r"ANGUILLA"),
    ("KN", r"KITTITIAN|ST\.? KITTS"),
    ("SC", r"SEYCHELL"),
    ("MU", r"MAURITI"),
    ("PA", r"PANAMA"),
    ("BZ", r"BELIZE"),
    ("MH", r"MARSHALL ISLANDS"),
    ("LR", r"LIBERIA"),
    ("WS", r"SAMOA"),
    ("LI", r"LIECHTENSTEIN"),
    ("MC", r"MONACO|MONEGASQUE"),
    ("LU", r"LUXEMBOURG"),
    ("IE", r"IRELAND|IRISH"),
    ("US", r"U\.S\.A|FEDERAL FINANCIAL INSTITUTIONS|UNITED STATES|AMERICAN|DELAWARE|NEW YORK|CALIFORNIA|NEVADA|WYOMING|"
           r"MARYLAND|OREGON|ARIZONA|PENNSYLVANIA|NORTH CAROLINA|TEXAS|FLORIDA"),
    ("CA", r"CANAD|ONTARIO|QUEBEC|BRITISH COLUMBIA"),
    ("AU", r"AUSTRALIA"),
    ("NZ", r"NEW ZEALAND"),
    ("SG", r"SINGAPOR|\bACRA\b|ACCOUNTING AND CORPORATE REGULATORY"),
    ("HK", r"HONG KONG"),
    ("CN", r"^CHINA|CHINESE"),
    ("TW", r"TAIWAN"),
    ("MY", r"MALAYSIA"),
    ("TH", r"^THAI"),
    ("IN", r"^INDIA"),
    ("PK", r"PAKISTAN"),
    ("BD", r"BANGLADESH"),
    ("AE", r"UNITED ARAB EMIRATES|EMIRATI|ABU DHABI|DUBAI|\bUAE\b"),
    ("SA", r"SAUDI"),
    ("KW", r"KUWAIT"),
    ("BH", r"BAHRAIN"),
    ("QA", r"QATAR"),
    ("JO", r"JORDAN"),
    ("LB", r"LEBAN"),
    ("IQ", r"IRAQ"),
    ("LY", r"LIBYA"),
    ("EG", r"EGYPT"),
    ("IL", r"ISRAEL"),
    ("CY", r"CYPR"),
    ("MT", r"MALT"),
    ("CH", r"SWISS|SWITZERLAND|ZURICH|GENEVA|ZUG\b"),
    ("DE", r"GERMAN|FRANKFURT|MUNICH|BERLIN|HAMBURG"),
    ("FR", r"FRANCE|FRENCH|PARIS|CENTRE DE FORMALITES"),
    ("BE", r"BELGI"),
    ("NL", r"NETHERLANDS|DUTCH"),
    ("AT", r"AUSTRIA"),
    ("DK", r"DENMARK|DANISH"),
    ("SE", r"SWEDEN|SWEDISH"),
    ("NO", r"NORW"),
    ("FI", r"FINLAND|FINNISH"),
    ("ES", r"SPAIN|SPANISH"),
    ("PT", r"PORTUG"),
    ("IT", r"ITAL"),
    ("PL", r"POLAND|POLISH"),
    ("TR", r"TURK"),
    ("ZA", r"SOUTH AFRICA"),
    ("NG", r"NIGERIA"),
    ("KE", r"KENYA"),
    ("ZM", r"ZAMBIA"),
    ("ZW", r"ZIMBABWE"),
    ("JP", r"JAPAN"),
    ("KR", r"KOREA"),
]
COMPILED = [(code, re.compile(rx)) for code, rx in RULES]

# Secrecy / offshore jurisdictions: a chain that ends here without a named owner is 'unknown'.
OFFSHORE = {"JE", "GG", "XC", "IM", "VG", "KY", "BM", "GI", "BS", "TC", "AI", "KN", "SC",
            "PA", "BZ", "MH", "LR", "WS", "LI"}


def to_iso(value):
    """Map a free-text country/registry/nationality to ISO2 ('UK' for the UK)."""
    if value is None:
        return None
    v = re.sub(r"\s+", " ", str(value)).strip().upper().strip(",")
    if not v:
        return None
    if re.fullmatch(r"[A-Z]{2}", v):
        return v
    # Multiple nationalities, e.g. "BRITISH,KENYAN": treat as UK if any part is UK
    # (conservative: we don't label a British national as a foreign owner).
    parts = [p.strip() for p in v.split(",") if p.strip()] if "," in v else [v]
    codes = [_match(p) for p in parts] if len(parts) > 1 and all(_match(p) for p in parts) else [_match(v)]
    if "UK" in codes:
        return "UK"
    return codes[0]


def _match(v):
    for code, rx in COMPILED:
        if rx.search(v):
            return code
    return None


if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        print(f"{to_iso(line)!s:5} {line.strip()}")
