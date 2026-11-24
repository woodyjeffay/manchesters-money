"""Small helpers shared across pipeline steps: cached HTTP and CSV discovery."""
import hashlib
import json
import time
from pathlib import Path

import requests

from config import CACHE, RAW

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "manchesters-money/0.1 (open data research)"


def cached_get_json(url, *, namespace, params=None, headers=None, auth=None,
                    min_interval=0.0, max_age_days=None):
    """GET a JSON URL, caching the response body under data/cache/<namespace>/.

    Returns (status_code, data). 404s are cached too so we don't re-ask.
    """
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    h = hashlib.sha1(key.encode()).hexdigest()
    path = CACHE / namespace / f"{h}.json"
    if path.exists():
        age_days = (time.time() - path.stat().st_mtime) / 86400
        if max_age_days is None or age_days < max_age_days:
            blob = json.loads(path.read_text())
            return blob["status"], blob["data"]

    for attempt in range(5):
        if min_interval:
            time.sleep(min_interval)
        r = SESSION.get(url, params=params, headers=headers, auth=auth, timeout=60)
        if r.status_code == 429:
            wait = 60 * (attempt + 1)
            print(f"  rate limited; sleeping {wait}s")
            time.sleep(wait)
            continue
        if r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            continue
        break

    data = r.json() if r.status_code == 200 and r.content else None
    if r.status_code in (200, 404):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"url": url, "params": params,
                                    "status": r.status_code, "data": data}))
    return r.status_code, data


def find_raw_csv(prefix):
    """Find the newest Land Registry CSV in data/raw whose name starts with prefix.

    Land Registry names files like OCOD_FULL_2026_11.csv / CCOD_FULL_2026_11.csv.
    """
    matches = sorted(p for p in RAW.glob("*.csv") if p.name.upper().startswith(prefix))
    if not matches:
        zips = sorted(p for p in RAW.glob("*.zip") if p.name.upper().startswith(prefix))
        hint = f" (found {zips[-1].name}: unzip it first)" if zips else ""
        raise SystemExit(f"No {prefix}*.csv in {RAW}{hint}")
    return matches[-1]


def normalise_postcode(pc):
    if not isinstance(pc, str):
        return None
    pc = pc.upper().replace(" ", "").strip()
    if len(pc) < 5:
        return None
    return pc[:-3] + " " + pc[-3:]
