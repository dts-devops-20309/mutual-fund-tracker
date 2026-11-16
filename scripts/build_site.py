#!/usr/bin/env python3
"""Assemble the static GitHub Pages site into _site/.

Copies site/ (HTML/CSS/JS) and writes _site/data.json: every tracked fund's NAV
history plus its latest monthly portfolio (and the month before it, so the page
can show what the fund bought and sold). Metrics are computed in the browser.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ROOT, load_funds, read_nav_csv  # noqa: E402

OUT = ROOT / "_site"


def portfolios_by_fund() -> dict[str, list[dict]]:
    """CODE -> that fund's monthly portfolios, newest first."""
    out: dict[str, list[dict]] = {}
    for path in sorted((DATA / "portfolio").glob("*.json"), reverse=True):
        doc = json.loads(path.read_text())
        for code, p in doc.get("funds", {}).items():
            out.setdefault(code, []).append({"month": doc["month"], **p})
    return out


def slim(p: dict | None) -> dict | None:
    if not p:
        return None
    return {k: p.get(k) for k in ("month", "as_of", "aum_cr", "asset_mix", "holdings", "source")}


def main() -> int:
    funds = load_funds()
    ports = portfolios_by_fund()
    status = json.loads((DATA / "nav_status.json").read_text()) if (DATA / "nav_status.json").exists() else {}

    out_funds = []
    for f in funds:
        series = read_nav_csv(DATA / "nav" / f"{f['code']}.csv")
        dates = sorted(series)
        hist = ports.get(f["code"], [])
        out_funds.append({
            **f,
            "launch": min(series) if series else None,
            "d": dates,
            "v": [series[d] for d in dates],
            "portfolio": slim(hist[0] if hist else None),
            "prev_portfolio": slim(hist[1] if len(hist) > 1 else None),
        })

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "amfi_nav_date": status.get("amfi_nav_date"),
        "funds": out_funds,
    }

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site", OUT)
    (OUT / "data.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    (OUT / ".nojekyll").write_text("")
    size_kb = (OUT / "data.json").stat().st_size / 1024
    with_port = sum(1 for f in out_funds if f["portfolio"])
    print(f"built {OUT} — {len(out_funds)} funds, {with_port} with holdings, data.json {size_kb:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
