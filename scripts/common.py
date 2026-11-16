"""Shared helpers for the fetch and build scripts (stdlib only)."""

from __future__ import annotations

import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
USER_AGENT = "Mozilla/5.0 (compatible; mutual-fund-tracker/1.0; personal NAV tracker, nightly)"


def load_funds() -> list[dict]:
    return json.loads((ROOT / "funds.json").read_text())


def http_get(url: str, attempts: int = 3, timeout: int = 60) -> bytes:
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001 - retry any network error
            if i == attempts - 1:
                raise
            print(f"retry {i + 1} for {url}: {exc}", file=sys.stderr)
            time.sleep(5 * (i + 1))
    raise AssertionError("unreachable")


def write_if_changed(path: Path, text: str) -> bool:
    if path.exists() and path.read_text() == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return True


def dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def read_nav_csv(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    with path.open() as fh:
        return {row["date"]: float(row["nav"]) for row in csv.DictReader(fh)}


def upsert_nav(code: str, points: dict[str, float]) -> int:
    """Merge points into data/nav/<code>.csv; returns number of new/changed dates."""
    path = DATA / "nav" / f"{code}.csv"
    series = read_nav_csv(path)
    changed = sum(1 for d, v in points.items() if series.get(d) != v)
    series.update(points)
    lines = ["date,nav"] + [f"{d},{series[d]}" for d in sorted(series)]
    write_if_changed(path, "\n".join(lines) + "\n")
    return changed
