#!/usr/bin/env python3
"""Nightly NAV fetch for the tracked mutual fund schemes.

Sources (public, no auth):
  - AMFI NAVAll.txt  https://portal.amfiindia.com/spages/NAVAll.txt
        the official daily NAV of every scheme in India (latest date only)
  - mfapi.in         https://api.mfapi.in/mf/<scheme_code>
        full daily NAV history per scheme, mirrored from AMFI

Each night: pull each scheme's history from mfapi.in (so missed days fill
themselves in), then add/confirm the latest NAV from AMFI. If mfapi.in is
down, the AMFI file alone still records today's NAV.

Outputs: data/nav/<CODE>.csv (date,nav) and data/nav_status.json.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, dump, http_get, load_funds, read_nav_csv, upsert_nav, write_if_changed  # noqa: E402

AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
MFAPI_BASE = "https://api.mfapi.in/mf/"
STALE_AFTER_DAYS = 4  # weekend + one market holiday


def fetch_mfapi(scheme_code: int) -> dict[str, float]:
    payload = json.loads(http_get(f"{MFAPI_BASE}{int(scheme_code)}"))
    out = {}
    for row in payload.get("data", []):
        d = datetime.strptime(row["date"], "%d-%m-%Y").date().isoformat()
        v = float(row["nav"])
        if v > 0:
            out[d] = round(v, 4)
    return out


def fetch_amfi(scheme_codes: set[int]) -> dict[int, tuple[str, float]]:
    """Latest (date, nav) per scheme code from AMFI's semicolon-separated file."""
    text = http_get(AMFI_URL).decode("utf-8", "replace")
    out = {}
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) < 5 or not parts[0].strip().isdigit():
            continue
        code = int(parts[0])
        if code not in scheme_codes:
            continue
        try:
            nav = float(parts[-2])
            d = datetime.strptime(parts[-1].strip(), "%d-%b-%Y").date().isoformat()
        except ValueError:
            continue
        out[code] = (d, round(nav, 4))
    return out


def main() -> int:
    funds = load_funds()
    status: dict = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "errors": []}
    new_points = 0

    for f in funds:
        try:
            new_points += upsert_nav(f["code"], fetch_mfapi(f["scheme_code"]))
        except Exception as exc:  # noqa: BLE001 - keep going, record in status
            status["errors"].append(f"mfapi {f['code']}: {exc}")
            print(f"::warning::mfapi.in failed for {f['code']}: {exc}")

    try:
        amfi = fetch_amfi({f["scheme_code"] for f in funds})
        for f in funds:
            if f["scheme_code"] not in amfi:
                status["errors"].append(f"amfi {f['code']}: scheme {f['scheme_code']} not in NAVAll.txt")
                continue
            d, v = amfi[f["scheme_code"]]
            new_points += upsert_nav(f["code"], {d: v})
        status["amfi_nav_date"] = max(d for d, _ in amfi.values()) if amfi else None
    except Exception as exc:  # noqa: BLE001
        status["errors"].append(f"amfi: {exc}")
        print(f"::warning::AMFI NAVAll.txt failed: {exc}")

    today = date.today()
    coverage = {}
    for f in funds:
        series = read_nav_csv(DATA / "nav" / f"{f['code']}.csv")
        if series:
            last = max(series)
            coverage[f["code"]] = {"first": min(series), "last": last, "points": len(series),
                                   "stale": (today - date.fromisoformat(last)).days > STALE_AFTER_DAYS}
    status["funds"] = coverage
    status["stale_funds"] = [c for c, v in coverage.items() if v["stale"]]
    if status["stale_funds"]:
        print(f"::warning::no NAV in the last {STALE_AFTER_DAYS} days: {', '.join(status['stale_funds'])}")

    # Rewrite the status file only when something besides the timestamp moved.
    path = DATA / "nav_status.json"
    prev = json.loads(path.read_text()) if path.exists() else {}
    strip = lambda s: {k: v for k, v in s.items() if k != "run_at"}  # noqa: E731
    if new_points or strip(status) != strip(prev):
        write_if_changed(path, dump(status))

    print(f"{new_points} new/changed NAV points")
    print(json.dumps(status, indent=2))
    # Fail the run only when nothing at all could be fetched.
    return 1 if len(status["errors"]) > len(funds) else 0


if __name__ == "__main__":
    sys.exit(main())
