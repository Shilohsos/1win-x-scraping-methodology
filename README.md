# 1win.ng & X/Twitter Scraping Methodology

**Author:** Wizard (Ferdinand Shiloh Hart)  
**Last Updated:** 2026-05-02  
**Repository:** Shilohsos/1win-x-scraping-methodology

---

## Overview

Complete, battle-tested methodologies for extracting real-time sports odds, social media data, **and fixture schedules** without official API access. Three independent but complementary systems:

### 1. 1win.ng Sports Odds Scraping
- **Tool:** CloakBrowser (stealth headless Chromium)
- **Proxy:** SA residential (82.29.245.95:6919)
- **Method:** DOM text extraction + line-based structured parsing
- **Scope:** Prematch fixture odds (1X2, totals, handicaps, corners, player props, correct score, etc.)
- **Coverage:** Championship, LaLiga, LaLiga2, Bundesliga, Premier League, Primeira Liga, and more

### 2. X/Twitter Real-Time Scraping
- **Tool:** Scrapling v0.4.7 (HTTP Fetcher backend)
- **Auth:** Session cookies (AUTH_TOKEN + CT0) via last30days pipeline
- **Method:** X private GraphQL SearchTimeline endpoint
- **Scope:** Real-time tweet collection for sports events, trends analysis
- **Performance:** ~2–3s query latency, 134+ tweets collected per test run

### 3. LiveScore Fixture API (NEW)
- **Tool:** Direct HTTP (curl / requests)
- **Proxy:** ❌ None required
- **Auth:** ❌ None required
- **Method:** Public JSON API endpoint
- **Scope:** 825+ fixtures/day across 263 competitions worldwide
- **Coverage:** PL, LaLiga, Serie A, Bundesliga, Ligue 1, MLS, and 257+ more
- **Status:** ✅ Production-ready — no blockers

### 1. 1win.ng Sports Odds Scraping
- **Tool:** CloakBrowser (stealth headless Chromium)
- **Proxy:** SA residential (82.29.245.95:6919)
- **Method:** DOM text extraction + line-based structured parsing
- **Scope:** Prematch fixture odds (1X2, totals, handicaps, corners, player props, correct score, etc.)
- **Coverage:** Championship, LaLiga, LaLiga2, Bundesliga, Premier League, Primeira Liga, and more

### 2. X/Twitter Real-Time Scraping
- **Tool:** Scrapling v0.4.7 (HTTP Fetcher backend)
- **Auth:** Session cookies (AUTH_TOKEN + CT0) via last30days pipeline
- **Method:** X private GraphQL SearchTimeline endpoint
- **Scope:** Real-time tweet collection for sports events, trends analysis
- **Performance:** ~2–3s query latency, 134 tweets collected per test run

---

## Repository Structure

```
├── README.md                              # This file
├── docs/
│   ├── 01-1win-scraping-methodology.md    # Complete 1win.ng methodology
│   ├── 02-x-twitter-scraping-methodology.md  # X/Twitter scraping methodology
│   ├── 03-livescore-fixture-methodology.md   # ⭐ NEW: LiveScore API methodology
│   └── 04-glossary.md                     # Terms and abbreviations
├── tests/
│   ├── eibar-vs-malaga-2026-05-02.md      # LaLiga2 test results (45 markets)
│   ├── man-utd-vs-liverpool-2026-05-03.md # Premier League test results (75+ markets)
│   └── livescore-api-validation-2026-05-02.md  # ⭐ NEW: LiveScore test report
├── scripts/
│   ├── 1win-odds-scraper.py               # Production-grade 1win scraper
│   ├── x-tweet-collector.py               # X/Twitter real-time collector
│   └── livescore-fixture-scraper.py       # ⭐ NEW: LiveScore API client
├── config/
│   ├── proxy-config.md                    # Proxy setup guide
│   └── cloakbrowser-setup.md              # CloakBrowser installation
└── findings/
    ├── three-tier-page-structure.md       # Page hierarchy discovery
    ├── parser-bleed-fixes.md              # Parser correction history
    └── tournament-dropdown-pattern.md     # Section expansion technique
```

---

## Quick Start

### 1win.ng Odds Scraping

```python
from cloakbrowser import launch

browser = launch(headless=True, stealth_args=True, humanize=True, proxy="http://user:pass@host:port")
page = browser.new_page()
page.goto("https://1win.ng/betting/prematch/soccer-18?time=1d")
# Expand league sections by clicking headers
# Click match rows to open full-market overlay
# Extract via page.inner_text("body") and parse with state machine
```

### X/Twitter Tweet Collection

```python
from scrapling import Fetcher
# Authenticate with AUTH_TOKEN + CT0 from last30days
# Discover current GraphQL query ID from X JS bundles
# POST to SearchTimeline endpoint
# Extract tweets from nested JSON response
```

### LiveScore Fixture API (NEW)

```bash
# Get tomorrow's fixtures as JSON
curl "https://prod-cdn-mev-api.livescore.com/v1/api/app/date/soccer/20260503/2?countryCode=GB&locale=en"

# Using the provided Python scraper
python scripts/scrape_livescore.py --date tomorrow --format json
```

```python
import requests
# No proxy, no auth — just GET the endpoint
resp = requests.get(
    "https://prod-cdn-mev-api.livescore.com/v1/api/app/date/soccer/20260503/2"
)
data = resp.json()  # 769 events, 238 competitions
```

---

## Key Discoveries

- **Three-tier page structure** on 1win.ng (Main → Aggregated → Dedicated)
- **Tournament dropdown pattern** for accessing sub-leagues (Section 6.1)
- **Interactive market expansion** via match row clicks (Section 6.2)
- **State-machine parser** with label→value odds pairing, `+99` stop condition
- **Parser bleed correction** for player-prop markets
- **X GraphQL query ID auto-discovery** from webpack bundles
- **Recursive tweet extraction** from nested JSON responses
- **LiveScore public API** — completely unauthenticated, no proxy needed, 800+ fixtures/day

---

## License

Private — All rights reserved. Authorized use by Master Ferdinand Shiloh Hart and delegated agents only.
