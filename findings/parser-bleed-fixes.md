# Finding: Parser Bleed Fixes

**Discovered:** 2026-05-02  
**Bug Type:** Market header boundary detection failure

---

## Bug: Player Prop Bleed

When parsing expanded match overlays, player-prop markets ("Player score or assist", "Player assist", "Player to score") were not recognized as new market headers. This caused player names to incorrectly attach to preceding markets (e.g., "Exact number of goals", "Odd/Even"), inflating their selection counts.

### Example
Before fix: `Exact number of goals` showed 445+ selections (including all player names).
After fix: Properly segmented into separate player markets.

### Fix
Extended the `is_market_header` function to include all observed player-prop headers:
- Player score or assist
- Player assist
- Player to score
- Player to score 2/3 and more
- Player to score header
- Player. Total shots over
- Player. Total shots on target over
- 1st player to score
- Last player to score

## Bug: Label→Value Confusion

Original parser treated consecutive numeric lines as odds values. Correct behavior: **label→value pairing**. Each line is either a label (1/x/2) or a value (the float after it).

### Fix
```python
last_label = None
for token in odds_block:
    if token in ("1", "2") or token.lower() == "x":
        last_label = token
    elif re.match(r'^\d+(\.\d+)?$', token):
        if last_label in odds:
            odds[last_label] = float(token)
        last_label = None
```

## Bug: AI Tips Bleed

Between every selection block, 1win inserts "AI tips (n/m)" lines followed by descriptive sentences. These caused parser to interpret sentences as market headers.

### Filter Rules
```python
# Skip AI tips line
re.match(r'^AI tips \(\d+/\d+\)', line)
# Skip descriptive sentences (end with .?! and length > 40)
re.match(r'^.{40,}[.?!]$', line)
# Skip category tab labels
tab_labels = {'All', 'Main', 'Total', 'Handicap', 'Halves', 'Players',
              'Corners', 'Goals/Score', 'Home Team', 'Away Team', 'Combo',
              'HT/FT', 'Cards/Penalties', 'Intervals', 'Correct Score'}
```

## Bug: Duplicate Market Sections

The expanded overlay renders core markets (Full time result, Double chance, BTTS) in two separate DOM sections (summary + full list).

### Fix
Deduplicate by `(market_name, selection_name, odd)` triple after initial parsing.
