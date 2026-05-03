# Sofascore EPL Injury Detection

## Methodology

Sofascore embeds **per-player injury data** in each player's profile endpoint — not in a team-level endpoint.

**Endpoint:** `https://api.sofascore.com/api/v1/player/{player_id}`

**Injury field (optional):**
```json
{
  "injury": {
    "reason": "Hamstring Injury",
    "status": "out",
    "expectedReturn": 28,
    "id": 21538,
    "startDateTimestamp": 1777248000,
    "updateDateTimestamp": 1777809640,
    "endDateTimestamp": 1779105640
  }
}
```

| Field | Meaning |
|-------|---------|
| `reason` | Human-readable injury description |
| `status` | `dayToDay`, `out`, or `sidelined` |
| `expectedReturn` | Expected days until return |
| `endDateTimestamp` | Unix timestamp of expected return date |

## Pipeline

```
1. EPL Season Players ──► Filter by team ──► Get all player IDs
   /api/v1/unique-tournament/17/season/76986/players

2. For each player ──► Fetch profile ──► Check for injury field
   /api/v1/player/{id}

3. Classify: 
   - Injured & OUT (status = "out" or "sidelined")
   - Playing through (status = "dayToDay")
   - Fit (no injury field)
```

## Tool

**Script:** `scripts/epl-scanner.py`

Requires:
- ScraperFC (botasaurus_driver) — browser-level scraping
- Webshare residential proxy — bypasses Sofascore's rate limiting
- Chrome with `--no-sandbox` flag

**Usage:**
```bash
# Full matchday scan (today's EPL matches)
/root/scraperfc_venv/bin/python scripts/epl-scanner.py

# Single team deep scan
/root/scraperfc_venv/bin/python scripts/epl-scanner.py --team "Liverpool FC"

# JSON output (for programmatic consumption)
/root/scraperfc_venv/bin/python scripts/epl-scanner.py --json

# Exclude squad-wide injury check (faster)
/root/scraperfc_venv/bin/python scripts/epl-scanner.py --lineups-only
```

## Performance

- Matchday scan (2 matches, lineups + injuries): ~2–3 minutes
- Single team squad scan (25+ players): ~2–3 minutes
- Bottleneck: each player profile is a separate browser API call

## Known Limitations

- Transfermarkt's `/verletzungen/` (injuries) pages are blocked by Cloudflare even through residential proxies
- Sofascore's `/api/v1/team/{id}/injuries` endpoint does **not exist** (returns 404)
- Injury data is only present on players who have it — no "no injury" flag
