# 1win.ng Odds Scraping — Complete Methodology

**Version:** 2.0 | **Date:** 2026-05-02 | **Author:** Wizard (Ferdinand Shiloh Hart)

---

## Table of Contents

1. [Overview & Tools](#1-overview--tools)
2. [Environment Setup](#2-environment-setup)
3. [Page Structure — Three Tiers](#3-page-structure--three-tiers)
4. [Tournament Dropdown Pattern](#4-tournament-dropdown-pattern)
5. [Core Parsing Engine](#5-core-parsing-engine)
6. [Interactive Market Expansion](#6-interactive-market-expansion)
7. [Tab-Based Market Extraction](#7-tab-based-market-extraction)
8. [URL Discovery Heuristics](#8-url-discovery-heuristics)
9. [Validation Checklist](#9-validation-checklist)
10. [Troubleshooting](#10-troubleshooting)
11. [League-Specific Notes](#11-league-specific-notes)
12. [Test Results Summary](#12-test-results-summary)

---

## 1. Overview & Tools

### Toolchain
| Component | Specification |
|-----------|--------------|
| Browser | CloakBrowser 0.3.26 (stealth headless Chromium) |
| Proxy | SA residential 82.29.245.95:6919 (auth: pzxyatji:tqz8zcybhmj7) |
| Python | 3.11+ |
| Method | DOM text extraction + line-based structured parsing |
| Parser | Two-mode state machine (Mode A: direct league; Mode B: aggregated) |
| Scope | Prematch fixtures, all available markets |

### Key Libraries
```bash
pip install cloakbrowser==0.3.26
# CloakBrowser installs bundled Chromium at ~/.cloakbrowser/chromium-*/
```

### Launch Configuration
```python
from cloakbrowser import launch

browser = launch(
    headless=True,
    stealth_args=True,
    humanize=True,          # Critical for aggregated page (967 KB HTML)
    proxy="http://user:pass@host:port"
)
page = browser.new_page()
page.set_default_timeout(60000)
```

### Proxy Verification
```python
page.goto("https://api.ipify.org", wait_until="domcontentloaded", timeout=30000)
ip = page.inner_text("body").strip()
assert "82.29.245" in ip, f"Proxy failed: got {ip}"
```

---

## 2. Environment Setup

### CloakBrowser Installation
```bash
python3 -m venv ~/cloakbrowser-venv
source ~/cloakbrowser-venv/bin/activate
pip install --upgrade pip
pip install cloakbrowser
cloakbrowser install
```

### Verify Installation
```bash
python -c "from cloakbrowser import launch; print('OK')"
```

### Storage Footprint
| Component | Size |
|-----------|------|
| CloakBrowser binary | ~697 MB |
| Python venv | ~173 MB |
| Total | ~870 MB |

---

## 3. Page Structure — Three Tiers

| Tier | URL Pattern | Purpose | Completeness |
|------|-------------|---------|--------------|
| **Tier 1 — Main** | `/betting` | Curated highlights carousel | ✗ Partial — shows ~5 fixtures/league, early kickoffs only |
| **Tier 2 — Aggregated** | `/betting/prematch/soccer-18?time=1d` | All soccer leagues in one view | ✓ Full for most leagues |
| **Tier 3 — Dedicated** | `/betting/prematch/soccer-18/{slug}-{id}?time=1d` | Single-league full fixture list | ✓ Most reliable when available |

### URL Selection Strategy
```
1. PRIMARY:   Dedicated league URL (if slug+ID known)
2. SECONDARY: Aggregated soccer page
3. TERTIARY:  Main /betting page (incomplete — use only for sanity checks)
```

### Time Filters
| Parameter | Behavior |
|-----------|----------|
| `?time=1d` | Next 24 hours (tomorrow) |
| `?time=2d` | Next 48 hours |
| `?time=3d` | Next 72 hours |
| `?time=1w` | Next 7 days |
| (none) | Default range (often matches `?time=3d`) |

### Verified Dedicated League URLs
| League | Slug+ID | Status |
|--------|---------|--------|
| Championship | `championship-930` | ✓ Works |
| Bundesliga | `bundesliga-1130` | ✓ Works |
| LaLiga | `laliga-11` | ✗ Broken — returns empty |
| Premier League | `premier-league-919` | ✗ Broken — returns empty |
| 2. Bundesliga | `bundesliga2-1460` | ✗ Broken — use dropdown instead |

---

## 4. Tournament Dropdown Pattern

This is the **critical technique** for accessing leagues that don't have working dedicated URLs or whose sections appear collapsed on the aggregated page.

### How It Works
1. Navigate to the aggregated soccer page (Tier 2)
2. Each league section has a **clickable header** (e.g., "Spain. LaLiga 2")
3. Clicking the header **expands** the section via XHR fetch
4. The URL does not change — content is dynamically loaded
5. This triggers an XHR fetch that populates the previously-empty section

### Implementation
```javascript
// Click a league header to expand it
const walker = document.createTreeWalker(
    document.body, NodeFilter.SHOW_TEXT, null, false
);
let node;
while (node = walker.nextNode()) {
    if (node.textContent.trim() === 'Spain. LaLiga 2') {
        let el = node.parentElement;
        while (el) {
            if (el.click) { el.click(); return; }
            el = el.parentElement;
        }
    }
}
```

### Wait Times
- After clicking header: **sleep(6)** seconds minimum
- For aggregated page initial load: **sleep(12)** seconds (967 KB HTML, heavy JS)
- Verify: `assert len(lines) > 300` after extraction

### Example Sequence
```
Before expand:
  Spain. LaLiga 2     ← collapsed, no matches visible
  Soccer
  Germany. 2nd Bundesliga

After clicking "Spain. LaLiga 2":
  Spain. LaLiga 2     ← expanded, matches now visible
  Soccer
  21:00
  •
  02/05/2026
  Eibar
  Malaga
  Full time result
  ...
  Germany. 2nd Bundesliga
```

---

## 5. Core Parsing Engine

### Text Extraction
```python
page.goto(url, wait_until="domcontentloaded", timeout=60000)
time.sleep(8)  # JS rendering time

raw_text = page.inner_text("body")
lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
```

### Mode A — Direct League Pages
Used when navigating directly to a league URL.

**Structure:**
```
Line L:   Country. League          ← league header (dot format)
Line L+1: Soccer                   ← sport
Line L+2: HH:MM                    ← KO time
Line L+3: •                        ← bullet delimiter
Line L+4: DD/MM/YYYY              ← date
Line L+5: Team 1
Line L+6: Team 2
Line L+7: Market label             ← e.g., "Full time result"
Line L+8: 1                        ← OPTION LABEL (not an odds value!)
Line L+9: 1.37                     ← actual odds
Line L+10: x
Line L+11: 5.0
Line L+12: 2
Line L+13: 7.5
Line L+14: +99                     ← margin line → end of match block
```

### Mode B — Aggregated Listings
Used on the aggregated soccer page.

**Detection:** Find section start by exact string match:
```python
def find_section(lines, header_text):
    for idx, line in enumerate(lines):
        if line.strip() == header_text:
            return idx
    return None
```

### State Machine — Odds Parsing
```python
odds = {"1": None, "x": None, "2": None}
last_label = None

while i < len(lines):
    token = lines[i]
    
    # Stop condition: margin line
    if re.match(r'^\+\d+$', token):
        i += 1
        break
    
    # Label detection
    if token in ("1", "2") or token.lower() == "x":
        last_label = "x" if token.lower() == "x" else token
        i += 1
        continue
    
    # Value detection — bind to last seen label
    if re.match(r'^\d+(\.\d+)?$', token):
        if last_label in odds:
            odds[last_label] = float(token)
        last_label = None
        i += 1
        continue
    
    break  # unexpected token
```

### CRITICAL: Label→Value Binding
- Consecutive numeric lines are NOT odds — they are **labels** followed by **values**
- Always: remember the last seen label (1/x/2) and bind the next float to it
- Reset label after assignment

---

## 6. Interactive Market Expansion

To access ALL markets for a match (not just 1X2):

### Step 1: Click Match Row
After the league section is expanded, click directly on the team name text to open a **full-screen overlay** containing all available markets.

```python
page.evaluate("""() => {
    const walker = document.createTreeWalker(
        document.body, NodeFilter.SHOW_TEXT, null, false
    );
    let node;
    while (node = walker.nextNode()) {
        if (node.textContent.trim() === 'Eibar') {
            let el = node.parentElement;
            for (let d = 0; d < 15; d++) {
                if (el && el.click) {
                    try { el.click(); return; } catch(e) {}
                }
                el = el.parentElement;
            }
        }
    }
}())""")
```

### Step 2: Wait for Overlay
```python
try:
    page.wait_for_load_state('networkidle', timeout=15000)
except:
    pass
time.sleep(8)  # Critical: overlay takes time to render all markets
```

### Step 3: Extract
After opening, the overlay contains all markets as rendered text. Extract via `page.inner_text("body")`.

### Market Volume by League
| Match | Lines | Markets | Selections |
|-------|-------|---------|------------|
| Eibar vs Malaga (LaLiga2) | ~504 | 20+ | 124+ |
| FC Porto vs Alverca (PL) | ~2,329 | ~60 | 1,030 |
| Man Utd vs Liverpool (PL) | ~2,515 | 75+ | 800+ |

---

## 7. Tab-Based Market Extraction

The overlay has a **tab bar** that organizes markets by category. Only the default view ("All" tab equivalent) is visible initially. To get everything, click each tab.

### Available Tabs (varies by league)
| Tab | Markets Included | Available For |
|-----|-----------------|---------------|
| Main | 1X2, DC, BTTS, totals, team goals | All matches |
| Total | Over/under lines, team totals | All matches |
| Handicap | Asian handicap lines | All matches |
| Halves | 1st/2nd half markets, HT/FT | All matches |
| Corners | Corner markets, Race to N | All matches |
| Goals/Score | Correct score, BTTS combos | All matches |
| Home Team | Home team-specific markets | All matches |
| Away Team | Away team-specific markets | All matches |
| Combo | Result+Total, Total+BTTS combos | All matches |
| Intervals | 1-10 minute markets | All matches |
| Players | Player props | ⚠️ Premier League+ only |
| HT/FT | Halftime/Fulltime | ⚠️ Premier League+ only |
| Cards/Penalties | Yellow cards, red cards | ⚠️ Premier League+ only |
| Correct Score | Full scorelines | ⚠️ Premier League+ only |

### Tab Clicking Implementation
```python
page.evaluate(f"""((t) => {{
    const allEls = document.querySelectorAll('button,div,span');
    for (let el of allEls) {{
        if (el.textContent.trim() === t) {{
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.y > 100 && r.y < 1000) {{
                el.click(); return;
            }}
        }}
    }}
}})('{tab_name}')""")
time.sleep(3)  # Wait for tab content to render
```

### Data Deduplication
Some markets appear in multiple tabs. Deduplicate by `(market_name, selection, odd)` triple after extraction.

---

## 8. URL Discovery Heuristics

When a dedicated league URL is unknown:

### Method 1: HTML Inspection
Search the aggregated page HTML for league links:
```python
html = page.evaluate("() => document.body.innerHTML")
links = re.findall(r'href=[\'"]([^\'"]*soccer-18[^\'"]*)[\'"]', html)
```

### Method 2: Pattern Guessing
League IDs follow no predictable pattern. Common attempts:
```
bundesliga-1130, championship-930, laliga-11, premier-league-919, 
laliga2-?, serie-a-?, league-1-?, eredivisie-?
```

### Method 3: Dropdown Expansion
The most reliable method — expand sections on the aggregated page to discover which leagues have fixtures.

---

## 9. Validation Checklist

Before trusting scraped data:

- [ ] **Proxy active** — `api.ipify.org` returns expected IP
- [ ] **Page loaded** — title contains "1win" and line count > 300
- [ ] **No geo-block** — text does NOT contain "Regional restrictions"
- [ ] **League header found** — exact match
- [ ] **Fixture count** — at least 1 match parsed; compare against expectations
- [ ] **Odds completeness** — every fixture has 1, x, 2 all non-null
- [ ] **Date sanity** — all dates match expected date
- [ ] **Duplicate check** — ensure same fixture isn't parsed twice
- [ ] **Overlay verification** — "Full time result" text present in overlay text
- [ ] **Tab presence** — at least Main tab found after overlay opens

---

## 10. Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Few lines (<30) | Proxy not applied OR JS incomplete | Verify IP via ipify; use humanize=True; increase sleep to 15s |
| League header not found | Page layout changed; wrong time filter | Print lines[:150]; search for country substring; adjust filter |
| Odds values are None | Parser consumed label but not value | Print raw lines around match; verify label→value order |
| 0 fixtures parsed but times exist | Section boundaries mis-detected | Verify stop condition regex; print the line that triggered break |
| Overlay not opening | Click not reaching match row element | Increase depth limit to 15; try clicking different parent levels |
| Tab not found | Tabs not available for this league | Accept as expected; log missing tabs per league |
| Page under-rendered | humanize=False on heavy page | Always use humanize=True for aggregated (967 KB) pages |
| Proxy IP shows local | CloakBrowser proxy param ignored | Set `os.environ['HTTP_PROXY']` and `HTTPS_PROXY` before launch |
| Stale/missing odds | Bot detection triggered | Rotate user-agent via stealth_args; add random delays |

---

## 11. League-Specific Notes

### LaLiga (Spain)
- **Direct URL:** `laliga-11` — BROKEN (returns empty)
- **Access:** Aggregated page only
- **Teams:** Osasuna, Barcelona FC, Valencia, Atletico Madrid, Villarreal, Levante, etc.
- **Note:** Barcelona appears as "Barcelona FC" (not "FC Barcelona")

### LaLiga 2 (Spain. LaLiga 2)
- **Direct URL:** Unknown/discovered via dropdown
- **Access:** Click "Spain. LaLiga 2" header on aggregated page
- **Tabs available:** 10 of 14 (no Players, HT/FT, Cards, Correct Score)

### Premier League
- **Direct URL:** `premier-league-919` — BROKEN
- **Access:** Click "England. Premier League" header on aggregated page
- **Tabs available:** All 14 available
- **Market volume:** Largest of any league (75+ markets, 800+ selections)
- **Player props:** 40+ players with shot, assist, goal, card markets

### Bundesliga
- **Direct URL:** `bundesliga-1130` — WORKS
- **2. Bundesliga:** Access via tournament dropdown from Bundesliga page
- **Interactive expansion:** Click match row → full overlay with 69 market categories, 949 selections

### Championship
- **Direct URL:** `championship-930` — WORKS
- **Full 12 fixtures per matchday**

### Primeira Liga (Portugal)
- **Access:** Click "Portugal. Primeira Liga" on aggregated page
- **Market volume:** 60 markets, 1,030 selections (richest observed)

---

## 12. Test Results Summary

### Test 1: Eibar vs Malaga (LaLiga2)
| Detail | Value |
|--------|-------|
| Date | 2026-05-02 |
| Kick-off | 21:00 WAT |
| Markets found | 45 categories across 10 tabs |
| Overlay lines | ~504 |
| Notable | Correct score, corners, handicaps present. No player props. |

### Test 2: Manchester United vs Liverpool (Premier League)
| Detail | Value |
|--------|-------|
| Date | 2026-05-03 |
| Kick-off | 16:30 WAT |
| Markets found | 75+ categories across 10 tabs |
| Overlay lines | ~2,515 |
| Notable | Full player props, HT/FT, yellow cards, shots on target, fouls, correct score |

### Key Findings
- Premier League matches have the **richest market profile**
- Player props only appear for top-tier leagues
- The tournament dropdown pattern (Section 4) is essential for sub-leagues
- Overlay expansion (Section 6) is mandatory for full market access
- Tab cycling (Section 7) extracts all available markets

---

*End of document. This methodology is a living document — update as new patterns are discovered.*
