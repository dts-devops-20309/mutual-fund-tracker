# Mutual Fund Tracker

Nightly NAV collection, monthly holdings and a plain-language performance dashboard for 7 Indian mutual funds (Direct Plan, Growth option), tracked since 1 April 2025.

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
- **Holdings drill-down** (fund page), from the fund house's official monthly portfolio:
  - the split between shares, bonds and cash, and fund size;
  - the top 10 stocks, and sectors summed over every holding;
  - what changed since the previous month: new stocks, stocks fully sold, biggest weight increases and decreases;
  - a searchable, sortable table of every holding.
- **"Do my funds own the same stocks?"** (overview): portfolio overlap between each pair of funds.

All returns are computed in the browser from `data/nav/*.csv`.

Build locally: `python scripts/build_site.py && python -m http.server -d _site`

## What runs

[`.github/workflows/fetch-data.yml`](.github/workflows/fetch-data.yml) runs every night at **00:00 IST** (18:30 UTC), after AMFI publishes the day's NAVs. You can also start it from the Actions tab. It:

1. **NAVs** ([`scripts/fetch_nav.py`](scripts/fetch_nav.py), standard library only):
   - pulls each scheme's full history from mfapi.in, so missed days fill themselves in;
   - adds or confirms the latest NAV from AMFI's official daily file.
2. **Holdings** ([`scripts/fetch_portfolio.py`](scripts/fetch_portfolio.py)): finds each fund house's latest monthly portfolio file. It downloads the file only when it is new, then parses it with [`scripts/portfolio_parse.py`](scripts/portfolio_parse.py). This step needs `openpyxl` and `xlrd` (`requirements.txt`). A failure here never blocks the NAV update.
3. Commits `data/` only when something changed.

Fund houses publish the previous month's portfolio within about 10 days of month-end, so holdings move forward once a month.

## Data sources

| Source | URL | Gives |
|---|---|---|
| AMFI daily NAV file | `https://portal.amfiindia.com/spages/NAVAll.txt` | Official latest NAV of every scheme in India |
| mfapi.in | `https://api.mfapi.in/mf/<scheme_code>` | Full daily NAV history per scheme (mirrored from AMFI) |
| Bandhan MF | `cmsnew.bandhanmutual.com/wp-json/finance-api/v1/posts/fund-information-portfolios` | Link to each scheme's latest monthly portfolio xlsx |
| Nippon India MF | `mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures` | Link to the monthly portfolio workbook (all schemes) |
| Motilal Oswal MF | `www.motilaloswalmf.com/.../api/search-documents.json?category=month end portfolio` | Link to the monthly portfolio workbook (all schemes) |

All of these are the plain, public download links that each site's own disclosure page uses.

**ICICI Prudential and HDFC** block automated requests: bot protection on the file list, and Akamai returns 403 for every page. For their 3 funds (`ICIINF`, `ICILC`, `HDFMID`), add holdings by hand once a month:

1. Download the scheme's monthly portfolio (Excel) from the fund house's *Statutory disclosures → Monthly portfolio* page.
2. Save it as `data/import/portfolio/<CODE>.xlsx` (or `.xls`). Overwrite last month's file.
3. Commit and push. The workflow parses it and the dashboard updates. A workbook with every scheme also works: the parser finds the right sheet by the fund name in `funds.json`.

## Data layout

```
funds.json               tracked funds (code, AMFI scheme code, ISIN, category)
data/nav/<CODE>.csv      date,nav – daily history, one row per NAV date
data/nav_status.json     last run, latest AMFI date, per-fund coverage and staleness
data/portfolio/<YYYY-MM>.json   parsed holdings per fund for that month (every line, % of fund, sector)
data/portfolio_status.json      latest month, source file and any error per fund
data/import/portfolio/<CODE>.xlsx   hand-downloaded portfolios (ICICI, HDFC)
```

*Not investment advice. Past performance does not guarantee future returns. NAV and portfolio data © AMFI and the respective fund houses, reproduced for personal tracking.*
