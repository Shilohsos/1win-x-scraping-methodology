# X/Twitter Real-Time Scraping — Complete Methodology

**Version:** 1.0 | **Date:** 2026-05-02 | **Author:** Wizard (Ferdinand Shiloh Hart)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Environment & Prerequisites](#2-environment--prerequisites)
3. [Authentication Strategy](#3-authentication-strategy)
4. [GraphQL Query ID Discovery](#4-graphql-query-id-discovery)
5. [Tweet Extraction & Parsing](#5-tweet-extraction--parsing)
6. [Real-Time Scraping Implementation](#6-real-time-scraping-implementation)
7. [Data Organization & Output](#7-data-organization--output)
8. [Rate Limiting & Performance](#8-rate-limiting--performance)
9. [Security & Stealth](#9-security--stealth)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Executive Summary

### Objective
Collect real-time tweets from X (Twitter) discussing sports events without using the official X API (no paid access, no developer account required).

### Solution
Use **Scrapling v0.4.7** — a Python web-scraping framework with multiple fetcher backends — to access X's private **GraphQL endpoints** using authenticated browser session cookies.

### Result
- ✅ 134 unique tweets collected across 4 Premier League fixtures
- ✅ ~2–3 second query latency
- ✅ Query ID auto-discovery adapts to X's periodic rotations
- ✅ No CAPTCHAs encountered

### Why This Works
X's web client uses GraphQL with query IDs that rotate periodically. By discovering the current Query ID at runtime from X's own JavaScript bundles, the scraper adapts automatically without hardcoding.

---

## 2. Environment & Prerequisites

### Requirements
| Component | Specification |
|-----------|--------------|
| OS | Ubuntu/Debian Linux |
| Python | 3.12 |
| Scrapling | v0.4.7 |
| Playwright | Pre-installed by Scrapling (Chromium 1208/1217) |
| Storage | ~1.5 GB for browser binaries |

### Virtual Environment Setup
```bash
python3 -m venv ~/scrapling-venv
source ~/scrapling-venv/bin/activate
pip install scrapling==0.4.7
```

### Verification
```bash
python -c "import scrapling; print(scrapling.__version__)"
# Expected: 0.4.7
```

### Scrapling Fetcher Options
| Fetcher | Use Case | Status |
|---------|----------|--------|
| `Fetcher()` | HTTP requests (GraphQL API calls) | ✅ Preferred |
| `DynamicFetcher()` | Full browser via Playwright | ⚠️ lxml issues |
| `StealthyFetcher()` | Anti-detection browser | ⚠️ lxml issues |

**Important:** Use `Fetcher` for X API calls — no JS rendering needed, fastest performance.

---

## 3. Authentication Strategy

### Problem
X's API requires authentication. Public endpoints return 403/401. The GraphQL search endpoint requires a valid user session.

### Solution
Reuse existing authenticated session cookies from the **last30days** pipeline.

### Cookie Location
```
File: ~/.config/last30days/.env
Keys: AUTH_TOKEN — main session token (short-lived, ~2 weeks)
      CT0        — CSRF token (longer-lived)
```

### Extraction
```python
from dotenv import load_dotenv
import os

load_dotenv('/root/.config/last30days/.env')
AUTH_TOKEN = os.getenv('AUTH_TOKEN')
CT0 = os.getenv('CT0')
```

### Cookie Header Format
```python
cookies = {
    'auth_token': AUTH_TOKEN,
    'ct0': CT0,
}
```

### Authentication Verification
Three tests confirmed working:
```bash
# Test 1: Homepage
curl -s -b 'auth_token=XXX; ct0=YYY' https://x.com/home

# Test 2: Tweet URL
curl -s -b 'auth_token=XXX; ct0=YYY' https://x.com/username/status/123

# Test 3: API endpoint
curl -s -b 'auth_token=XXX; ct0=YYY' https://x.com/i/api/1.1/trends/place.json?id=23424908
```

### Token Lifespan
- AUTH_TOKEN expires after approximately **2 weeks**
- last30days pipeline auto-refreshes by visiting x.com and extracting fresh cookies
- If scraping fails with 401/403, refresh via last30days

---

## 4. GraphQL Query ID Discovery

### Problem
GraphQL query IDs (e.g., `BqWLX1Tjvgh6eSZWEMH_kw`) are **NOT stable**. X rotates them periodically as part of obfuscation. Hardcoding is fragile.

### Solution
Discover the current SearchTimeline query ID at runtime by downloading and scanning X's JavaScript bundles.

### Bundle URLs
```
https://abs.twimg.com/responsive-web/client-web/main.[hash].js
https://abs.twimg.com/responsive-web/client-web/vendor.[hash].js
https://abs.twimg.com/responsive-web/client-web/HomeTimeline.[hash].js
```

### Automated Discovery
```python
import re, urllib.request

bundle_urls = [
    'https://abs.twimg.com/responsive-web/client-web/main.js',
    'https://abs.twimg.com/responsive-web/client-web/vendor.js',
]

query_id = None
for url in bundle_urls:
    response = urllib.request.urlopen(url)
    js_content = response.read().decode('utf-8', errors='ignore')
    matches = re.findall(
        r'SearchTimeline[^}]*?queryId:"([A-Za-z0-9_-]+)"',
        js_content
    )
    if matches:
        query_id = matches[0]
        break
```

### Known Query ID
As of 2026-05-02: `BqWLX1Tjvgh6eSZWEMH_kw`

### Rotation Handling
If the query ID stops working (API returns errors or empty results), re-run the discovery routine. It takes ~2 seconds to fetch 1–2 bundles and find the new ID. Automate at the start of each scraping session.

---

## 5. Tweet Extraction & Parsing

### GraphQL Request Structure
```
POST https://twitter.com/i/api/graphql/{queryId}/SearchTimeline
```

### Required Headers
```python
headers = {
    'Content-Type': 'application/json',
    'x-csrf-token': CT0,
    'x-twitter-active-user': 'yes',
    'x-twitter-client-language': 'en',
    'referer': 'https://x.com/search?q=...',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/120.0.0.0 Safari/537.36',
}
```

### Request Body
```json
{
  "variables": {
    "rawQuery": "premier league fixtures today",
    "count": 20,
    "cursor": null,
    "querySource": "typed_query",
    "product": "Top"
  }
}
```

### Response Structure
```json
{
  "data": {
    "search_by_raw_query": {
      "timeline": {
        "instructions": [
          {
            "type": "TimelineAddEntries",
            "entries": [
              {
                "entryId": "tweet-123",
                "content": {
                  "item": {
                    "tweet": { ... full tweet object ... }
                  }
                }
              }
            ]
          }
        ]
      }
    }
  }
}
```

### Extraction Algorithm
```python
def extract_tweets_from_response(resp_json):
    tweets = []
    timeline = (resp_json.get('data', {})
                .get('search_by_raw_query', {})
                .get('timeline', {}))
    for instruction in timeline.get('instructions', []):
        for entry in instruction.get('entries', []):
            item = entry.get('content', {}).get('item', {})
            tweet = item.get('tweet')
            if tweet:
                tweets.append(tweet)
    return tweets
```

### Tweet Object Fields
| Field | Description |
|-------|-------------|
| `rest_id` | Tweet ID |
| `full_text` | Tweet body |
| `legacy.created_at` | Timestamp |
| `legacy.user.screen_name` | Author handle |
| `legacy.favorite_count` | ❤️ count |
| `legacy.retweet_count` | 🔄 count |
| `legacy.lang` | Language code |

### Pagination
```python
cursor = None
all_tweets = []
while True:
    response = fetch_tweets(query, cursor=cursor, count=50)
    batch = extract_tweets(response)
    all_tweets.extend(batch)
    
    new_cursor = find_cursor_in_response(response)
    if not new_cursor or new_cursor == cursor:
        break
    cursor = new_cursor
```

Cursor is found in entries with `entryId` containing `cursor-bottom`.

---

## 6. Real-Time Scraping Implementation

### Workflow
1. **Authenticate** — load cookies from `~/.config/last30days/.env`
2. **Discover Query ID** — fetch X JS bundles, regex-search for SearchTimeline
3. **Construct search queries** for target fixture(s)
4. **For each query:**
   - POST to GraphQL with Scrapling Fetcher
   - Extract tweets from nested JSON
   - Append to results
   - Wait 10s (rate-limit friendly)
5. **Deduplicate** — use `tweet_id` as unique key
6. **Save** — write raw JSON to timestamped file

### Scrapling Fetcher Usage
```python
from scrapling import Fetcher

fetcher = Fetcher()

response = fetcher.post(
    url=f'https://twitter.com/i/api/graphql/{query_id}/SearchTimeline',
    json=payload,
    headers={
        'x-csrf-token': ct0,
        'x-twitter-active-user': 'yes',
    },
    cookies=cookies,
)

data = response.json()
```

### Search Queries for Premier League
```python
queries = [
    "Premier League fixtures today",
    "Arsenal vs Fulham today",
    "Newcastle vs Brighton today",
    "#AFC #FFC",
    "#NUFC #BHAFC",
]
```

---

## 7. Data Organization & Output

### Raw Output
```
File: /tmp/pl_x_live_{unix_timestamp}.json
Size: ~250 KB (92 tweets)
Format: Raw JSON array (full tweet objects from X)
```

### Tweet Categorization
```python
match_groups = {
    'Arsenal vs Fulham': ['arsenal', 'fulham', '#afc', '#ffc'],
    'Newcastle vs Brighton': ['newcastle', 'brighton', '#nufc', '#bhafc'],
    'General PL Discussion': ['premier league', 'epl'],
}
```

### Human-Readable Output
```
════════════════════════════════════════════════
 Arsenal vs Fulham  (27 tweets)
════════════════════════════════════════════════

[1] @luckyshopcom — Sat May 02 11:44:11 +0000 2026  💬 0 🔄 0
     Futbol dolu bir Cumartesi...

[2] @Betbaba_ng — Sat May 02 11:43:52 +0000 2026  💬 0 🔄 1
     ⚽🔥 It's Premier League matchday...
```

---

## 8. Rate Limiting & Performance

### Observed Limits
| Parameter | Value |
|-----------|-------|
| Requests/hour | ~900 per session |
| Max tweets/request | 100 (count parameter) |
| Burst threshold | ~5 req/second |

### Recommended Configuration
| Parameter | Value |
|-----------|-------|
| Queries per cycle | 8 |
| Delay between queries | 10 seconds |
| Total cycle duration | ~80 seconds |
| Daily request estimate | ~650 queries/day |

### Optimization Options
1. Merge queries with OR for broader coverage
2. Reduce count from 20 to 15 for freshness
3. Parallel sessions using 3–4 different AUTH_TOKENs
4. Faster polling during match windows only

---

## 9. Security & Stealth

### Header Spoofing
```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'sec-ch-ua': '"Chromium";v="120", "Google Chrome";v="120"',
    'sec-ch-ua-mobile': '?0',
}
```

### Cookie Management
- AUTH_TOKEN & CT0 stored in `~/.config/last30days/.env` (chmod 600)
- Never commit these to git
- Rotate every 2 weeks via last30days refresh

### Detection Risk
Using GraphQL API with a valid user session is indistinguishable from real browser traffic when headers match. No CAPTCHAs encountered in testing.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 401 Unauthorized | AUTH_TOKEN expired | Refresh via last30days pipeline |
| 403 CSRF | Missing x-csrf-token header | Ensure CT0 is set as x-csrf-token |
| Empty results | Query ID rotated | Re-run discovery script |
| lxml crash | lxml unavailable | Switch to Fetcher (HTTP only) |
| JSON decode error | HTML error page returned | Check response.text for login page |
| 429 Too Many Requests | Rate limited | Increase delay to 15–20s |
| Non-PL tweets | Keyword pollution | Filter by lang='en', exclude #IPL, #T20 |
| Parser bleed | JSON structure changed | Print full response, adapt extractor |

### Diagnostic Commands
```bash
# Check X access
python -c "from scrapling import Fetcher; f=Fetcher(); r=f.get('https://x.com/home', cookies={'auth_token':'xxx','ct0':'yyy'}); print(r.status_code)"

# Find current query ID manually
curl -s 'https://abs.twimg.com/responsive-web/client-web/main.js' | grep -o 'SearchTimeline[^"]*"[A-Za-z0-9_-]*'

# Verify cookie works
curl -s -b 'auth_token=...; ct0=...' https://x.com/i/api/1.1/trends/place.json?id=23424908
```

### Critical Files
| File | Purpose |
|------|---------|
| `/tmp/scrape_pl_live.py` | Main production scraper |
| `/tmp/scrape_tweets_graphql.py` | Query ID discovery |
| `/tmp/scrape_tweets_extract.py` | Tweet extraction function |
| `/tmp/scrape_pl_org.py` | Tweet categorization |
| `/tmp/pl_x_live_*.json` | Raw tweet data |

---

*End of document.*
