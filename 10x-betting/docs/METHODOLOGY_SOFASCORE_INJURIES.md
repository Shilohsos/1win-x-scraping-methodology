# Methodology: Match-Day Injury Detection via Sofascore

**Source:** [Sofascore API](https://www.sofascore.com/api-documentation) (Unofficial JSON API)
**Tier:** Free (no API key required)
**Cost:** $0
**Auth:** None (browser-based access via SA residential proxy)
**Last Updated:** 2026-05-03

---

## Why Sofascore Over API-Football

| Factor | Sofascore | API-Football |
|--------|-----------|-------------|
| Cost | Free | Paid ($50+/month) |
| Auth | No key needed | Requires RapidAPI subscription |
| Data quality | Official partnerships | Aggregated |
| Proxy required | Yes (SA residential) | No |
| Player profiles | Rich (position, injury, stats) | Basic |

---

## Approach: Match-Day Squad Only

We **only** check players in the match-day squad (starting XI + substitutes). Full-squad scans are expensive (~100+ API calls per team) and irrelevant — only the 20 players dressing for the match matter for edge calculation.

### Data Flow

```
Sofascore /unique-tournament/{id}/season/{id}/events/last/{page}
  └─  Get today's EPL matches → match IDs, team names

Sofascore /event/{match_id}/lineups
  └─  Get starting XI + substitutes → player IDs

Sofascore /player/{player_id}
  └─  Check `injury` field → {reason, status, expectedReturn, endDateTimestamp}
```

### Injury Response Shape

```json
{
  "player": {
    "name": "Chadi Riad",
    "injury": {
      "reason": "Knock Injury",
      "status": "sidelined",
      "expectedReturn": "2026-05-20",
      "endDateTimestamp": 1777766400
    }
  }
}
```

### Extracted Fields

| Field | Status | Meaning |
|-------|--------|---------|
| `reason` | String | Injury type (e.g., "Hamstring Injury", "Ankle Injury") |
| `status` | `out` / `sidelined` / `dayToDay` | Severity classification |
| `expectedReturn` | Date string | Estimated recovery date |
| `endDateTimestamp` | Unix timestamp | Alternative return representation |

---

## Implementation

**File:** `src/collectors/injuries.py` — `SofascoreInjuryScanner` class

### Key Design Decisions

1. **Persistent browser** — Single `botasaurus_driver.Driver` instance reused across all API calls. Avoids ~2s Chrome launch overhead per call.

2. **Player cache** — `SofascoreClient.player(pid)` caches profiles in memory per session. Same player appearing in multiple matches only fetched once.

3. **Match-day only** — `get_lineups(match_id)` fetches only players in the squad. No full-squad scan.

4. **Proxy** — SA residential proxy (`82.29.245.95:6919`) required. Direct requests to `api.sofascore.com` return 403 without proper TLS fingerprint.

### Performance

| Action | Calls | Time | Notes |
|--------|-------|------|-------|
| Fetch today's matches | 6 | ~2s | 1 live + 5 scheduled pages |
| Fetch lineups | 1 | ~2s | Per match |
| Fetch player profiles | 40 | ~35s | 2 teams × 20 players, cached |

**Total per match:** ~40s (first scan) → ~5s (cached)

---

## Failure Modes

| Scenario | Behaviour |
|----------|-----------|
| No lineups published yet | Returns empty results gracefully |
| Proxy down | Returns empty, logs error |
| Player API returns 403 | Returns {} for that player, logs warning |
| No matches today | Returns empty dict |
| Match already finished | Lineups still available (no problem) |

---

## Integration with Signal Engine

The collector returns:

```python
{
    "home": [
        {"player": "Chadi Riad", "injury": "Knock Injury",
         "status": "sidelined", "return_date": "2026-05-20"},
        ...
    ],
    "away": [...]
}
```

The signal engine `_eval_availability()` reads:
- `injuries["home"]` / `injuries["away"]` — list of injured players
- Each item's `"player"` key for display
- Count used for injury impact score: `min(total * 0.1, 0.5)`

---

## Setup

1. No API key required
2. Ensure `botasaurus_driver` is installed (in `scraperfc_venv`)
3. SA residential proxy configured in `injuries.py` (hardcoded for now)
4. ScraperFC venv with Chrome `--no-sandbox` wrapper

---

## Limitations

- **Slow on first run** (~35-40s per match for uncached player profiles)
- **Browser dependency** — requires Chrome/botasaurus_driver, can't run with plain HTTP
- **Match-day only** — doesn't detect injuries to players not in the squad (e.g., long-term absentees already ruled out)
- **Sofascore API is unofficial** — may break if they change their endpoint structure
