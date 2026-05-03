# Methodology: Full-Squad Injury Detection via Sofascore

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
| Squad coverage | Full squad (25-30 players) | Only match-day roster |

---

## Approach: Full Squad Scan

We scan **every player registered to a team** in the EPL season, not just the match-day squad. This catches long-term absentees already ruled out before matchday — critical for edge calculation.

### Why Full Squad Matters

A match-day-only scan misses players who:
- Were dropped from the squad at selection (already ruled out)
- Are on long-term injury (out for months, not in training)
- Returned to training but not yet match-fit

These are exactly the players most relevant for edge detection.

---

## Data Flow

### Step 1: Load full competition roster (1 API call, cached)

```
GET /unique-tournament/17/season/76986/players
  ↓
{team_id: [player_id, ...]}  ← 528 players across 20 EPL teams
```

Cached in memory for the session. Only re-fetched when the scanner is re-initialized.

### Step 2: For each match, resolve team IDs from match event

```
GET /event/{match_id}
  ↓
{homeTeam: {id: 35, name: "Bournemouth"}, awayTeam: {id: 38, name: "Crystal Palace"}}
```

### Step 3: Scan each team's full roster

For each player in the team's squad:
```
GET /player/{player_id}
  ↓
{player: {name: "...", injury: {...} or null}}
```

Each player profile is cached — no redundant fetches if the same player appears in multiple matches.

---

## Injury Data Format

### Sofascore Response (player profile)

```json
{
  "player": {
    "name": "Eddie Nketiah",
    "injury": {
      "reason": "Strain Injury",
      "status": "sidelined",
      "expectedReturn": "2026-06-20",
      "endDateTimestamp": 1780358400
    }
  }
}
```

### Status Values

| Status | Meaning | Included in Results |
|--------|---------|-------------------|
| `out` | Confirmed unavailable | ✅ Yes |
| `sidelined` | Out indefinitely | ✅ Yes |
| `dayToDay` | Questionable, could play | ❌ No (too speculative) |

---

## Implementation

**File:** `src/collectors/injuries.py` — `SofascoreInjuryScanner` class

### Key Design Decisions

1. **Persistent browser** — Single `botasaurus_driver.Driver` instance reused across all API calls. Avoids ~2s Chrome launch overhead per call.

2. **Full squad roster** — `_load_squads()` fetches all 528 EPL players in one call, groups by team. Cached for the session.

3. **Per-player cache** — `SofascoreClient.player(pid)` caches profiles in memory. Each player fetched at most once per session regardless of which team they play for.

4. **Proxy** — SA residential proxy (`82.29.245.95:6919`) required. Direct requests to `api.sofascore.com` return 403.

### Performance

| Action | Calls | Time | Notes |
|--------|-------|------|-------|
| Load squad roster | 1 | ~2s | 528 players, cached per season |
| Scan 1 team (25-30 players) | 25-30 | ~18-22s | First scan per team, cached |
| Scan 1 match (2 teams) | 50-60 | ~40-45s | Both teams, cold cache |
| Cached re-scan | 0 | ~0s | Player profiles cached |

**Total for 3-match day:** ~2-3 minutes cold (then instant for re-scans within session)

---

## Integration with Signal Engine

```python
collector = InjuriesCollector()
result = await collector.get_for_match(match_id=14024023)
# Returns:
{
    "home": [],
    "away": [
        {"player": "Chadi Riad", "injury": "Knock Injury",
         "status": "sidelined", "return_date": "2026-05-20"},
        {"player": "Jean Philippe Mateta", "injury": "Knee Injury",
         "status": "sidelined", "return_date": "2026-03-13"},
        # ... 2 more
    ]
}
```

Signal engine `_eval_availability()` reads `injuries["home"]` / `injuries["away"]` as lists and calculates impact score: `min(total * 0.1, 0.5)`.

---

## Failure Modes

| Scenario | Behaviour |
|----------|-----------|
| No squad data for team | Returns empty list, logs warning |
| Player profile 403 | Returns `{}` for that player, continues |
| Proxy connection lost | Browser reconnection fails, returns partial results |
| No matches today | Returns empty dict |
| Season ID changes | Squad roster returns empty; update `SEASON_ID` |

---

## Setup

1. No API key required
2. `botasaurus_driver` installed (in `scraperfc_venv`)
3. SA residential proxy configured (hardcoded in `injuries.py`)
4. Chrome `--no-sandbox` wrapper for root execution

---

## Limitations

- **Sofascore API is unofficial** — may break with endpoint changes
- **Browser dependency** — requires Chrome/botasaurus, not pure HTTP
- **Season ID must be updated** — changes each season
- **Slow first scan** — ~40s per match for uncached profiles
- **No injury history** — only shows current injury; no past/future predictions
