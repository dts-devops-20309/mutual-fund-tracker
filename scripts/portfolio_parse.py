"""Parse a SEBI-format monthly portfolio statement (xlsx / xls) into holdings.

Every Indian AMC publishes the same statement layout, one sheet per scheme:
a title block naming the scheme and "as on <date>", then a header row like

    Name of the Instrument | ISIN | Industry / Rating | Quantity |
    Market/Fair Value (Rs. in Lakhs) | % to Net Assets

followed by section rows ("Equity & Equity related", "Debt Instruments",
"TREPS", "Net Receivables / (Payables)") and sub-total rows. This module finds
the header by its column names, so per-AMC differences in column order, extra
columns or title rows do not matter.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

ISIN_RE = re.compile(r"^IN[A-Z0-9]{10}$|^[A-Z]{2}[A-Z0-9]{9}\d$")
DATE_PATTERNS = [
    (re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-./]+([A-Za-z]{3,9})[\s\-.,/]+(\d{4})"), "dmy"),
    (re.compile(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})"), "mdy"),
    (re.compile(r"(\d{1,2})[\-/.](\d{1,2})[\-/.](\d{4})"), "dmy_num"),
]


def norm(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def load_sheets(path: Path) -> dict[str, list[list]]:
    """Sheet name -> rows (lists of cell values). Supports .xlsx and legacy .xls."""
    # Sniff the format: Nippon serves real xlsx (a zip, "PK") with an .xls name.
    with path.open("rb") as fh:
        is_zip = fh.read(2) == b"PK"
    if not is_zip:
        import xlrd  # noqa: PLC0415

        book = xlrd.open_workbook(str(path), on_demand=True)
        return {s.name: [s.row_values(i) for i in range(s.nrows)] for s in book.sheets()}
    import openpyxl  # noqa: PLC0415

    # Pass a file object: openpyxl rejects paths ending in .xls even when the content is xlsx.
    with path.open("rb") as fh:
        wb = openpyxl.load_workbook(fh, read_only=True, data_only=True)
        return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def sheet_title_text(rows: list[list], n: int = 15) -> str:
    return " ".join(norm(c) for r in rows[:n] for c in r if norm(c))


def find_scheme_sheet(sheets: dict[str, list[list]], title: str, exclude: list[str] = ()) -> str | None:
    """Sheet with a holdings header whose title block has a cell starting with
    `title` (case-insensitive) and containing none of `exclude`."""
    simple = lambda x: re.sub(r"[\s\-]+", " ", norm(x).lower())  # noqa: E731 - "Mid-Cap" == "Mid Cap"
    t = simple(title)
    with_header = []
    for name, rows in sheets.items():
        hdr = _find_header(rows)
        if not hdr:
            continue
        with_header.append(name)
        for r in rows[:hdr[0]]:
            for c in r:
                cell = simple(c)
                # Some AMCs prefix the title, e.g. "Scheme Name : HDFC Mid Cap Fund".
                cell = re.sub(r"^(scheme\s*name|name of (the )?scheme|portfolio of)\s*[:\-]?\s*", "", cell)
                if cell.startswith(t) and not any(x.lower() in cell for x in exclude):
                    return name
    # A single-scheme file (typical of hand-downloaded ICICI/HDFC files) whose
    # title wording differs slightly: use its only holdings sheet.
    return with_header[0] if len(with_header) == 1 else None


def parse_as_of(text: str) -> str | None:
    m = re.search(r"as (?:on|at)\s*:?\s*(.{6,30})", text, re.I)
    candidates = [m.group(1)] if m else []
    candidates.append(text)
    for c in candidates:
        for rx, kind in DATE_PATTERNS:
            mm = rx.search(c)
            if not mm:
                continue
            try:
                if kind == "dmy":
                    d, mon, y = mm.groups()
                    return datetime.strptime(f"{d} {mon[:3]} {y}", "%d %b %Y").date().isoformat()
                if kind == "mdy":
                    mon, d, y = mm.groups()
                    return datetime.strptime(f"{d} {mon[:3]} {y}", "%d %b %Y").date().isoformat()
                d, mo, y = mm.groups()
                return datetime(int(y), int(mo), int(d)).date().isoformat()
            except ValueError:
                continue
    return None


def _find_header(rows: list[list]) -> tuple[int, dict[str, int]] | None:
    for i, r in enumerate(rows[:60]):
        cols: dict[str, int] = {}
        for j, c in enumerate(r):
            t = norm(c).lower()
            if not t:
                continue
            if "name" in cols and "isin" in cols and "pct" in cols and "industry" in cols and "value" in cols:
                break
            if "name" not in cols and re.search(r"name of (the )?(instrument|issuer|security|company)|^instrument|^security name|^company", t):
                cols["name"] = j
            elif "isin" not in cols and t.startswith("isin"):
                cols["isin"] = j
            elif "pct" not in cols and re.search(r"%|percent|perc\.?\s*to|to net assets|to nav", t) and "yield" not in t and "ytm" not in t:
                cols["pct"] = j
            elif "industry" not in cols and re.search(r"industry|rating|sector", t):
                cols["industry"] = j
            elif "value" not in cols and re.search(r"market\s*/?\s*fair value|market value|fair value", t):
                cols["value"] = j
                cols["value_unit"] = 100 if "crore" in t else 1  # stored in lakhs unless crores
        if {"name", "isin", "pct"} <= cols.keys():
            return i, cols
    return None


CASH_WORDS = ("treps", "tri-party", "triparty", "reverse repo", "repo", "cblo", "net receivable", "net current",
              "cash", "margin", "net payable", "other current", "clearing corporation")
DEBT_WORDS = ("debt", "bond", "debenture", "money market", "certificate of deposit", "commercial paper",
              "treasury", "government", "g-sec", "gsec", "state development", "sdl", "securitised", "ncd")
EQUITY_WORDS = ("equity", "shares", "stock", "listed / awaiting", "listed/awaiting", "unlisted", "foreign securities",
                "adr", "gdr", "reit", "invit")
OTHER_WORDS = ("derivative", "futures", "options", "mutual fund units", "units of", "index fund", "etf")


def _section(text: str, current: str) -> str:
    t = text.lower()
    for kind, words in (("other", OTHER_WORDS), ("cash", CASH_WORDS), ("debt", DEBT_WORDS), ("equity", EQUITY_WORDS)):
        if any(w in t for w in words):
            return kind
    return current


def parse_scheme_sheet(rows: list[list]) -> dict:
    """Holdings, asset mix, AUM and as-of date from one scheme's sheet."""
    hdr = _find_header(rows)
    if not hdr:
        raise ValueError("no header row with instrument name, ISIN and % to net assets")
    hi, cols = hdr
    title = sheet_title_text(rows[:hi + 1], hi + 1)
    as_of = parse_as_of(title)

    raw: list[dict] = []
    section = "equity"
    aum_lakhs = None
    for r in rows[hi + 1:]:
        cells = [norm(c) for c in r]
        if not any(cells):
            continue
        name = cells[cols["name"]] if cols["name"] < len(cells) else ""
        isin = cells[cols["isin"]].upper() if cols["isin"] < len(cells) else ""
        pct_cell = r[cols["pct"]] if cols["pct"] < len(r) else None
        industry = cells[cols["industry"]] if "industry" in cols and cols["industry"] < len(cells) else ""
        low = name.lower()
        # Section labels sit in the name column or in a leading "(A)" style column.
        label = " ".join(c for c in cells[:cols["name"] + 1] if c)
        try:
            pct = float(str(pct_cell).replace("%", "").replace(",", "")) if pct_cell not in (None, "") else None
        except ValueError:
            pct = None

        if re.match(r"^(grand )?total|^net assets|^total net assets", low) or low.startswith("sub total") or low.startswith("subtotal"):
            if re.match(r"^grand total|^net assets|^total net assets", low) and "value" in cols and cols["value"] < len(r):
                try:
                    aum_lakhs = float(str(r[cols["value"]]).replace(",", "")) * cols["value_unit"]
                except ValueError:
                    pass
            continue
        if ISIN_RE.match(isin) and pct is not None:
            kind = section
            if kind == "cash":  # an ISIN under a cash heading is a money-market paper
                kind = "debt"
            raw.append({"name": name, "isin": isin, "industry": industry, "pct": pct, "kind": kind})
            continue
        if pct is None:
            section = _section(label, section)
            continue
        # Rows with a % but no ISIN: cash, TREPS, receivables, margin money, etc.
        if any(w in low for w in CASH_WORDS):
            raw.append({"name": name, "isin": "", "industry": "", "pct": pct, "kind": "cash"})
        else:
            section = _section(label, section)

    if not raw:
        raise ValueError("header found but no holdings rows")
    # Some AMCs store 8.54% as 0.0854.
    total = sum(h["pct"] for h in raw)
    if total < 2:
        for h in raw:
            h["pct"] *= 100
    merged: dict[str, dict] = {}
    for h in raw:
        key = h["isin"] or f"{h['kind']}:{h['name'].lower()}"
        if key in merged:
            merged[key]["pct"] += h["pct"]
        else:
            merged[key] = dict(h)
    holdings = sorted(merged.values(), key=lambda h: -h["pct"])
    for h in holdings:
        h["pct"] = round(h["pct"], 4)
        if not h["industry"]:
            h.pop("industry")

    mix = {"equity_pct": 0.0, "debt_pct": 0.0, "other_pct": 0.0}
    for h in holdings:
        if h["kind"] != "cash":
            mix[f"{h['kind']}_pct"] += h["pct"]
    mix = {k: round(v, 2) for k, v in mix.items()}
    mix["cash_pct"] = round(max(0.0, 100 - sum(mix.values())), 2)  # TREPS, receivables, etc. (residual)

    return {
        "as_of": as_of,
        "aum_cr": round(aum_lakhs / 100, 2) if aum_lakhs else None,
        "asset_mix": mix,
        "holdings": holdings,
    }
