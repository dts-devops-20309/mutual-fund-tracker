#!/usr/bin/env python3
"""Monthly portfolio (holdings) collection from each fund house's official
SEBI monthly portfolio disclosure.

Automatic sources (plain GETs of the files each AMC's public download page links):
  bandhan  WordPress JSON on cmsnew.bandhanmutual.com -> one xlsx per scheme
  nippon   the disclosures page HTML -> one workbook with every scheme
  motilal  the downloads search JSON -> one workbook with every scheme

ICICI Prudential and HDFC block automated requests, so funds with
"source": "manual" read a file you download yourself and save as
data/import/portfolio/<CODE>.xlsx (or .xls). The same parser handles all of them.

Output: data/portfolio/<YYYY-MM>.json  {"month", "funds": {CODE: {...}}}
        data/portfolio_status.json     what was found per fund, and errors
A file is only rewritten when its content changes.
"""

from __future__ import annotations

import html
import json
import re
import sys
import tempfile
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, dump, http_get, load_funds, write_if_changed  # noqa: E402
import portfolio_parse as pp  # noqa: E402

BANDHAN_API = "https://cmsnew.bandhanmutual.com/wp-json/finance-api/v1/posts/fund-information-portfolios?bypass_pagination=true"
NIPPON_PAGE = "https://mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures"
NIPPON_BASE = "https://mf.nipponindiaim.com"
MOTILAL_BASE = "https://www.motilaloswalmf.com"
MOTILAL_SEARCH = MOTILAL_BASE + "/content/aem-cloud-dept-backend-motilal-oswal/api/search-documents.json"
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


# ---------- discovery: each returns the URL of the latest portfolio file ----------

def discover_bandhan(title: str) -> str:
    posts = json.loads(http_get(BANDHAN_API)).get("data", [])
    for p in posts:
        if html.unescape(p.get("title", "")).strip().lower() == title.lower():
            files = (p.get("acf_fields") or {}).get("fund_files") or []
            if files and files[0].get("file", {}).get("url"):
                return files[0]["file"]["url"]
    raise LookupError(f"no Bandhan portfolio post titled {title!r}")


def discover_nippon(_title: str) -> str:
    page = http_get(NIPPON_PAGE).decode("utf-8", "replace").replace("\u200b", "")
    best = None
    rx = re.compile(r"Monthly\s+portfolio\s+for\s+the\s+month\s+of\s+([A-Za-z]+)\s+(\d{4}).{0,400}?href=\"([^\"]+)\"", re.I | re.S)
    for mon, year, href in rx.findall(page):
        m = MONTHS.get(mon[:3].lower())
        if not m or "FORTNIGHT" in href.upper():
            continue
        key = (int(year), m)
        if best is None or key > best[0]:
            best = (key, urllib.parse.urljoin(NIPPON_BASE, html.unescape(href)))
    if not best:
        raise LookupError("no 'Monthly portfolio for the month of' link on the Nippon page")
    return best[1]


def discover_motilal(_title: str) -> str:
    found = []
    for year in (date.today().year, date.today().year - 1):
        q = urllib.parse.urlencode({"year": year, "category": "month end portfolio", "month": "", "type": "mf"})
        for r in json.loads(http_get(f"{MOTILAL_SEARCH}?{q}")).get("results", []):
            if not r.get("title", "").lower().startswith("scheme portfolio details"):
                continue
            try:
                published = datetime.strptime(r.get("publishDate", ""), "%d-%m-%Y").date()
            except ValueError:
                continue
            found.append((published, MOTILAL_BASE + urllib.parse.quote(r["path"])))
        if found:
            break
    if not found:
        raise LookupError("no 'scheme portfolio details' file in the Motilal downloads search")
    return max(found)[1]


DISCOVER = {"bandhan": discover_bandhan, "nippon": discover_nippon, "motilal": discover_motilal}


# ---------- main ----------

def main() -> int:
    funds = load_funds()
    status_path = DATA / "portfolio_status.json"
    prev = json.loads(status_path.read_text()) if status_path.exists() else {}
    prev_funds = prev.get("funds", {})
    status: dict = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "funds": {}}
    downloads: dict[str, Path] = {}  # url -> local temp file (Nippon/Motilal share one workbook)
    tmp = Path(tempfile.mkdtemp(prefix="portfolios-"))
    results: dict[str, dict] = {}  # month -> {code: portfolio}

    for f in funds:
        code, cfg = f["code"], f.get("portfolio") or {}
        src = cfg.get("source")
        st: dict = {"source": src}
        try:
            if src == "manual":
                files = sorted((DATA / "import" / "portfolio").glob(f"{code}.xls*"))
                if not files:
                    st["note"] = f"waiting for data/import/portfolio/{code}.xlsx"
                    status["funds"][code] = st
                    continue
                path, url = files[0], None
            else:
                url = DISCOVER[src](cfg["title"])
                st["url"] = url
                # Same file as last successful run: nothing new to parse.
                if prev_funds.get(code, {}).get("url") == url and prev_funds[code].get("month") and not prev_funds[code].get("error"):
                    status["funds"][code] = prev_funds[code]
                    continue
                if url not in downloads:
                    p = tmp / f"{len(downloads)}.bin"
                    p.write_bytes(http_get(url, timeout=120))
                    downloads[url] = p
                path = downloads[url]
            sheets = pp.load_sheets(path)
            name = pp.find_scheme_sheet(sheets, cfg["title"], cfg.get("exclude", []))
            if not name:
                raise LookupError(f"no sheet titled {cfg['title']!r} in {path.name}")
            parsed = pp.parse_scheme_sheet(sheets[name])
            if not parsed["as_of"]:
                raise ValueError("could not read the 'as on' date")
            month = parsed["as_of"][:7]
            eq = sum(1 for h in parsed["holdings"] if h["kind"] == "equity")
            results.setdefault(month, {})[code] = {**parsed, "source": url}
            st.update({"month": month, "as_of": parsed["as_of"], "sheet": name, "stocks": eq})
            print(f"{code}: {month} — {eq} stocks, equity {parsed['asset_mix']['equity_pct']}%, sheet {name}")
        except Exception as exc:  # noqa: BLE001 - one AMC failing must not stop the others
            st["error"] = f"{type(exc).__name__}: {exc}"
            # Keep last good month so the status still says what's on file.
            for k in ("month", "as_of"):
                if prev_funds.get(code, {}).get(k):
                    st[k] = prev_funds[code][k]
            print(f"::warning::{code} portfolio: {st['error']}")
        status["funds"][code] = st

    changed = 0
    for month, by_code in results.items():
        path = DATA / "portfolio" / f"{month}.json"
        doc = json.loads(path.read_text()) if path.exists() else {"month": month, "funds": {}}
        doc["funds"].update(by_code)
        doc["funds"] = dict(sorted(doc["funds"].items()))
        changed += write_if_changed(path, dump(doc))

    strip = lambda s: {k: v for k, v in s.items() if k != "run_at"}  # noqa: E731
    if changed or strip(status) != strip(prev):
        write_if_changed(status_path, dump(status))
    print(json.dumps(status, indent=2))
    auto = [f["code"] for f in funds if (f.get("portfolio") or {}).get("source") in DISCOVER]
    failed = [c for c in auto if "error" in status["funds"].get(c, {})]
    return 1 if auto and len(failed) == len(auto) else 0


if __name__ == "__main__":
    sys.exit(main())
