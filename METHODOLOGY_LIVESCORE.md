# LiveScore Scraping Methodology

**Status:** ✅ Production-ready
**Last tested:** 2026-05-02
**Tool:** Direct HTTP (curl / requests)
**Proxy required:** ❌ No — works from VPS directly
**API key required:** ❌ No
**Rate limit:** ~15-30 req/min (observed)

---

## 1. Overview

LiveScore exposes a **public, unauthenticated JSON API** that returns complete fixture data for any date. No browser automation, no proxy rotation, no API keys — just HTTP GET.

**Base endpoint:**
```
https://prod-cdn-mev-api.livescore.com/v1/api/app/date/soccer/{DATE}/{ZONE}?countryCode=GB&locale=en
```

- `{DATE}` — `YYYYMMDD` (e.g., `20260503`)
- `{ZONE}` — `2` (soccer/football zone ID)

---

## 2. Discovery

1. Open https://www.livescore.com/en/
2. Network tab → filter by `api`
3. Request: `mev-api...date/soccer/20260502/2`
4. Copy full URL — no auth headers required

---

## 3. Request Format

### Required Headers
None strictly required, but polite headers recommended:

```bash
curl "https://prod-cdn-mev-api.livescore.com/v1/api/app/date/soccer/20260502/2?countryCode=GB&locale=en" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  -H "Accept: application/json" \
  -H "Referer: https://www.livescore.com/"
```

### Query Parameters
| Parameter | Value | Required |
|-----------|-------|----------|
| `countryCode` | `GB` (for England focus) | ❌ optional |
| `locale` | `en` | ❌ optional |

**Note:** The API works without any headers or params — just the bare URL returns 200.

---

## 4. Response Structure

```json
{
  "Ts": 1777753274,
  "Stages": [
    {
      "Sid": "21997",
      "Snm": "Premier League",
      "Scd": "premier-league",
      "Cnm": "England",
      "CnmT": "england",
      "Csnm": "England",
      "Ccd": "england",
      "CompId": "65",
      "CompN": "Premier League",
      "Events": [
        {
          "Eid": "1529156",
          "Pids": { "112": "SBTE_2_1024044230", "8": "1529156", "29": "1529156" },
          "T1": [ { "ID": "2810", "Nm": "Manchester United", "Abr": "MUN", ... } ],
          "T2": [ { "ID": "3340", "Nm": "Liverpool", "Abr": "LIV", ... } ],
          "Tr1": 3,
          "Tr2": 0,
          "Eps": "FT",
          "Esid": 6,
          "Et": 1,
          "Esd": 20260502160000,
          "EO": 874496893,
          "EOX": 874496893,
          "Spid": 1,
          "Pid": 8,
          ...
        }
      ]
    }
  ]
}
```

### Key Fields

| Field | Meaning |
|-------|---------|
| `Stages` | Array of competitions (PL, LaLiga, etc.) |
| `Snm` | Competition name |
| `Cnm` | Country |
| `Events` | Array of matches |
| `T1` / `T2` | Team objects (home/away) |
| `Nm` | Team name |
| `Abr` | Team abbreviation |
| `Tr1` / `Tr2` | Scores (home/away) |
| `Eps` | Period/status (NS, LIVE, HT, FT, etc.) |
| `Esd` | Date/time as `YYYYMMDDHHMMSS` |
| `Eid` | Event ID (unique per match) |
| `Pids` | Provider IDs (may link to odds feeds) |

---

## 5. Date Strategy

LiveScore uses the **local timezone of the matches**, not UTC. For Nigeria:

```python
# Nigeria is WAT (UTC+1) — LiveScore returns local kickoff times
# Example: "16:30" in data is 16:30 local time, not UTC
```

**Dates to query:**
- `today` — `20260502` (current day)
- `tomorrow` — `20260503` (next day)
- `+1` — `20260504` (day after)

**Format:** `YYYYMMDD` as integer in URL path.

---

## 6. Parser

### Python Implementation

```python
import requests
import json

def fetch_livescore(date_str="20260502"):
    """Fetch LiveScore data for a given date."""
    url = f"https://prod-cdn-mev-api.livescore.com/v1/api/app/date/soccer/{date_str}/2"
    params = {"countryCode": "GB", "locale": "en"}

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def parse_events(data):
    """Extract flat list of events with key fields."""
    events = []
    for stage in data.get("Stages", []):
        comp = stage.get("Snm", "?")
        country = stage.get("Cnm", "?")
        for evt in stage.get("Events", []):
            events.append({
                "event_id": evt.get("Eid"),
                "competition": comp,
                "country": country,
                "home_team": evt.get("T1", [{}])[0].get("Nm", ""),
                "away_team": evt.get("T2", [{}])[0].get("Nm", ""),
                "home_score": evt.get("Tr1"),
                "away_score": evt.get("Tr2"),
                "status": evt.get("Eps"),
                "kickoff": evt.get("Esd"),
                "provider_ids": evt.get("Pids", {}),
            })
    return events

# Usage
data = fetch_livescore("20260503")
events = parse_events(data)
for e in events:
    if "Manchester" in e["home_team"] or "Manchester" in e["away_team"]:
        print(f"{e['home_team']} {e['home_score']} - {e['away_score']} {e['away_team']} [{e['status']}]")
```

---

## 7. Status Codes (`Eps`)

| Code | Meaning |
|------|---------|
| `NS` | Not Started — upcoming |
| `1H` | First half live |
| `HT` | Half-time |
| `2H` | Second half live |
| `FT` | Full-time |
| `ET` | Extra time |
| `P` | Penalties |
| `LIVE` | Generic live indicator |
| `POSTP` | Postponed |
| `CANC` | Cancelled |

---

## 8. Known Quirks

1. **No pagination** — all events in one response (~450KB for today)
2. **Rate limiting** — if you get HTTP 429, back off 30s
3. **Timezone** — kickoff times are **local to the match venue**, not UTC
4. **Event IDs change daily** — same teams tomorrow = different `Eid`
5. **Provider IDs (`Pids`)** — likely map to betting data sources; keep for future integration
6. **Competition name variations** — LiveScore uses `"LaLiga"` (single word, no space). Multiple countries have identically-named competitions (e.g., "Premier League" exists in England, Bahrain, Canada, Jamaica). Always pair `Snm` (competition name) with `Cnm` (country name) for precise league identification.

---

## 9. Validation Checklist

- [ ] Date format is `YYYYMMDD` (e.g., `20260503`, not `2026-05-03`)
- [ ] Request succeeds (HTTP 200) within 15s
- [ ] Response is valid JSON (>400KB for full day)
- [ ] `Stages` array has >200 competitions (full dataset)
- [ ] Specific match found (e.g., `Manchester United` vs `Liverpool`)
- [ ] Status `Eps` is one of known codes (`NS`, `LIVE`, `FT`, `HT`, etc.)
- [ ] Kickoff `Esd` is 14-digit timestamp

---

## 10. Production Script

See `scripts/scrape_livescore.py` in this repository:

```bash
python scripts/scrape_livescore.py --date 20260503 --format json
```

Outputs:
- `stdout` — JSON lines (one event per line)
- `--output livescore_YYYY-MM-DD.json` — full file

---

## 11. Comparison With Other Sources

| Source | LiveScore | 1win.ng | Sofascore |
|--------|-----------|---------|-----------|
| Access | Direct API | Browser scrape | ❌ Blocked |
| Proxy needed | ❌ No | ✅ Yes | ✅ Yes (blocked) |
| API key | ❌ No | ❌ No | ❌ No |
| Events/day | 825+ | Variable | ❌ Blocked |
| Data quality | Structured JSON | HTML + JS | ❌ Blocked |
| Odds included | ❌ No | ✅ Yes | ❌ No |

**LiveScore is our fixture backbone. Pair with 1win.ng for odds.**

---

*This methodology is locked. Do not modify without approval.*
