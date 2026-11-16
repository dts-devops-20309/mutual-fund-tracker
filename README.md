# Mutual Fund Tracker

Nightly NAV collection and a plain-language performance dashboard for 7 Indian mutual funds (Direct Plan, Growth option), tracked since 1 April 2025.

**Dashboard:** https://mchittineni.github.io/mutual-fund-tracker/

## Funds tracked

| Code | Fund | Category | AMFI code |
|---|---|---|---|
| ICIINF | ICICI Prudential Infrastructure Fund | Sectoral | 120621 |
| BANSC | Bandhan Small Cap Fund | Small Cap | 147946 |
| NIPMID | Nippon India Growth Mid Cap Fund | Mid Cap | 118668 |
| HDFMID | HDFC Mid Cap Fund | Mid Cap | 118989 |
| MOSMID | Motilal Oswal Midcap Fund | Mid Cap | 127042 |
| ICILC | ICICI Prudential Large Cap Fund | Large Cap | 120586 |
| NIPLC | Nippon India Large Cap Fund | Large Cap | 118632 |

All are Direct Plan, Growth option. ISINs are in [`funds.json`](funds.json). To track another fund, add a row there with its AMFI scheme code.

## Dashboard

A static page (`site/`, no build tools or dependencies) deployed by [`.github/workflows/pages.yml`](.github/workflows/pages.yml) after every data change and every nightly fetch.

- **Overview:**
  - each fund's return over 1 day, 1 week, 2 weeks, 1 month, 3 months, 6 months, 1 year and since April 2025 (total and per year);
  - a ranked "which funds did best" chart;
  - a sortable table, filterable by category, with 12-month sparklines.
- **Fund page** (click any fund):
  - an NAV chart with range buttons;
  - what ₹10,000 invested on 1 Apr 2025 is worth today;
  - the biggest drop from a high, and trailing returns;
  - the gain or loss for every day, week, fortnight, month, quarter, half-year and year since April 2025, with the best, worst and average periods, plus a table view.

  Half-years and years follow India's financial year (April to March).

All returns are computed in the browser from `data/nav/*.csv`.

Build locally: `python scripts/build_site.py && python -m http.server -d _site`

## What runs

[`.github/workflows/fetch-data.yml`](.github/workflows/fetch-data.yml) runs every night at **00:00 IST** (18:30 UTC), after AMFI publishes the day's NAVs. You can also start it from the Actions tab. It runs [`scripts/fetch_nav.py`](scripts/fetch_nav.py), which:

1. pulls each scheme's full NAV history from mfapi.in, so any missed days fill themselves in;
2. adds or confirms the latest NAV from AMFI's official daily file. If mfapi.in is down, today's NAV is still recorded;
3. commits `data/` only when something changed.

It uses only the Python standard library and makes 8 HTTP requests a night.

## Data sources

| Source | URL | Gives |
|---|---|---|
| AMFI daily NAV file | `https://portal.amfiindia.com/spages/NAVAll.txt` | Official latest NAV of every scheme in India |
| mfapi.in | `https://api.mfapi.in/mf/<scheme_code>` | Full daily NAV history per scheme (mirrored from AMFI) |

## Data layout

```
funds.json               tracked funds (code, AMFI scheme code, ISIN, category)
data/nav/<CODE>.csv      date,nav – daily history, one row per NAV date
data/nav_status.json     last run, latest AMFI date, per-fund coverage and staleness
```

## Coming next

Holdings drill-down from each fund house's official monthly portfolio disclosure. It will show every stock and sector, what changed since last month, and how much the funds overlap. The dashboard code for it is already in place; the fetcher is not.

*Not investment advice. Past performance does not guarantee future returns. NAV data © AMFI and the respective fund houses, reproduced for personal tracking.*
