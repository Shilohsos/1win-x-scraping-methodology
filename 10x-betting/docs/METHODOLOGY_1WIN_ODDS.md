# Methodology: 1win.ng Odds Scraping via CloakBrowser

**Source:** [1win.ng](https://1win.ng/betting) — Nigerian-facing sportsbook
**Tier:** Free (no account required for prematch odds)
**Cost:** $0 (proxy subscription separate)
**Auth:** None (public page, SA proxy for geo-bypass)
**Last Updated:** 2026-05-03

---

## Why CloakBrowser

1win.ng is an SPA (Single Page Application) — odds data is NOT present in the raw HTML. It is rendered client-side via JavaScript after page load. Simple HTTP requests (`curl`, `requests`, `aiohttp`) return only the shell HTML with `window.INITIAL_DATA` — no odds.

A full browser is required. CloakBrowser provides:
- **Stealth anti-detection** — proper TLS fingerprint, WebGL, canvas fingerprints
- **Built-in proxy support** — routes all traffic through SA residential IP
- **Playwright-compatible API** — `.goto()`, `.inner_text()`, `.evaluate()`

---

## Approach

### Data Flow

```
1. Launch CloakBrowser with SA residential proxy
2. Navigate to aggregated soccer page
   → https://1win.ng/betting/prematch/soccer-18?time=2d
3. Wait for JS render (12s initial load)
4. Detect and expand collapsed league sections
5. Extract DOM text
6. Parse with state-machine: label → value binding for 1/X/2 markets
7. Return structured odds dict
```

### Proxy

SA residential proxy `82.29.245.95:6919` (user: `pzxyatji`, pass: `tqz8zcybhmj7`) is mandatory. Direct access from Nigeria returns geo-block.

```
Proxy IP check: https://api.ipify.org → 82.29.245.95 (South Africa)
Geo-block symptom: page returns < 10 lines with "Regional restrictions"
```

---

## Implementation

**File:** `src/collectors/odds.py` — `OddsCollector` class

### Key Design Decisions

1. **CloakBrowser, not Playwright/Chrome headless** — CloakBrowser provides stealth + proxy in one package. Playwright's bundled Chromium lacks the SA IP without system-level proxy config.

2. **Aggregated page, not league-specific URLs** — `https://1win.ng/betting/prematch/soccer-18?time=2d` covers all soccer leagues. Direct league URLs (e.g., `/laliga-11?time=1d`) are unreliable and often return empty.

3. **12s initial wait** — The page is ~967 KB of JS bundles. The `domcontentloaded` event fires before odds are rendered. A fixed wait of 12s is required before extracting text.

4. **Collapsed section detection** — Some leagues start collapsed (header visible, matches hidden). The parser checks if match patterns (time → bullet → date → teams) appear within 10 lines of the header. If not, it clicks the header DIV to expand and waits 6s.

5. **6s click wait** — After clicking a collapsed section, the SPA loads match data via XHR. A 6s wait is required for the data to render in DOM.

6. **State-machine parser** — Odds appear as label→value pairs in the text:
   ```
   1       ← label
   1.69    ← value
   x       ← label
   3.96    ← value
   2       ← label
   4.92    ← value
   +99     ← margin line (stop)
   ```
   The parser reads tokens in order: capture the most recent label (`1`, `x`, `2`), assign the next float value to it, reset when odds are complete. Stops at `+NN` margin lines.

7. **Retry on Cloudflare** — Up to 3 retry attempts with exponential backoff if page lines < 100 (Cloudflare challenge indicator).

### Performance

| Step | Time | Notes |
|------|------|-------|
| Browser launch | ~3s | CloakBrowser headless |
| Page load + render | 12s | Fixed wait after `domcontentloaded` |
| Section expansion (if needed) | +6s | Per collapsed league |
| Text extraction + parse | <1s | DOM read + regex |

**Total per scrape:** ~15-30s depending on number of collapsed sections

---

## Text Parsing — Label→Value State Machine

```python
def _parse_odds(lines, home_team, away_team):
    # 1. Find consecutive team name lines
    for i, line in enumerate(lines):
        if line == home_team and lines[i+1] == away_team:
            match_idx = i
            break

    # 2. Scan up to 20 lines ahead for 1/x/2 label
    for j in range(match_idx + 2, min(len(lines), match_idx + 22)):
        if lines[j] in ("1", "2") or lines[j].lower() == "x":
            start = j
            break

    # 3. State machine: label → value
    odds = {"1": None, "x": None, "2": None}
    last_label = None
    while i < len(lines):
        token = lines[i]
        if re.match(r'^\+\d+$', token):
            break
        if token in ("1", "2") or token.lower() == "x":
            last_label = "x" if token.lower() == "x" else token
            i += 1; continue
        if re.match(r'^\d+(\.\d+)?$', token):
            if last_label in odds:
                odds[last_label] = float(token)
            last_label = None
            i += 1; continue
        break

    if all(v is not None for v in odds.values()):
        return {"home": odds["1"], "draw": odds["x"], "away": odds["2"]}
    return None
```

**Important:** Some leagues (Serie A) show the "Total" (Over/Under) market before "Full time result". The parser does NOT search for the market header text — it scans for the first `1`/`x`/`2` label token after team names and starts the state machine from there.

---

## Known Issues & Mitigations

| Issue | Cause | Fix |
|-------|-------|-----|
| Cloudflare challenge | Intermittent JS challenge | Retry up to 3x; reload and wait 12s each |
| Section collapsed | Not all leagues expand by default | Detect expansion state before clicking |
| "Total" market before 1X2 | Serie A page layout | Don't search for "Full time result"; scan for first 1/x/2 label |
| Missing Bundesliga fixtures | Aggregated page omits some | Use main `/betting` page as fallback |
| Zero odds parsed | Wrong URL or geo-block | Check IP; verify page has 100+ lines |
| Page load hangs | SPA JS bundle error | timeout 60s; retry on exception |

---

## Full Market Extraction (Detail Page)

For matches requiring **all markets** (not just 1X2), the match card's click navigates to a dedicated detail page:

```
/betting/match/sport/{team1}-vs-{team2}-{eventId}
```

This page has ~2000+ lines with all markets rendered server-side:
- Full time result, BTTS, Double chance, Odd/Even
- Over/Under (0.5 to 5.5+)
- Asian Handicap ladder (-2.5 to +2.5)
- Correct Score (all permutations)
- 1st half / 2nd half markets
- Corners (result, total, handicap, race-to-N)
- Yellow cards, red cards, fouls, shots on target
- Player props (anytime scorer, 2+ goals, assists, cards)
- HT/FT combos, Result+Total combos

---

## Setup

```
1. pip install cloakbrowser          # stealth Chromium
2. Configure SA proxy in .env or code
3. Proxy: 82.29.245.95:6919
4. User: pzxyatji / Pass: tqz8zcybhmj7
5. No 1win account required
```

---

## Limitations

1. **Text-based parsing is fragile** — DOM layout changes break positioning
2. **12s+2x6s fixed waits** — not event-driven; could be optimized
3. **No live odds** — currently only prematch; live odds update via WebSocket (unexplored)
4. **CloakBrowser dependency** — cannot run with plain HTTP tools
5. **Rate limiting** — 1win may throttle frequent page loads (not observed yet)
