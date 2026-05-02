# Finding: Tournament Dropdown Pattern

**Discovered:** 2026-05-02  
**Method:** 2. Bundesliga access testing

---

## The Problem

Some leagues (e.g., 2. Bundesliga, LaLiga 2) cannot be accessed via:
- Dedicated league URLs (most return empty pages)
- The aggregated soccer page (shows the section header but no matches)
- Direct URL guessing (league IDs are unpredictable)

## The Solution

1. Navigate to a **working league page** (e.g., Bundesliga at `/bundesliga-1130`)
2. Find the **tournament selector** — labeled "Choose a tournament" or showing league list
3. Click the **desired sub-league** (e.g., "2nd Bundesliga")
4. The page triggers an **XHR fetch** and replaces the match list in-place
5. **The URL does not change**

## How It Works

The "Choose a tournament" dropdown lists all leagues within the current sport+country context. Clicking a league name triggers an XHR request that dynamically loads that league's fixtures without a page reload.

## League Section Expansion (Aggregated Page)

On the aggregated soccer page, league sections are **collapsed by default**. They appear as headers (e.g., "Spain. LaLiga 2 / Soccer") with no matches visible beneath them. Clicking the **header text** expands the section.

### Pattern
```
Before click:
  Spain. LaLiga 2
  Soccer
  Germany. 2nd Bundesliga    ← next section immediately

After click on "Spain. LaLiga 2":
  Spain. LaLiga 2
  Soccer
  21:00
  •
  02/05/2026
  Eibar
  Malaga
  Full time result
  1
  2.04
  ...
  +99
  Germany. 2nd Bundesliga     ← next section
```

## Implementation

```python
page.evaluate("""() => {
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
}()""")
time.sleep(6)  # Wait for XHR
```

## When to Use

Use this technique when:
- ✅ A league section appears on the aggregated page but has no matches
- ✅ A direct league URL returns empty
- ✅ You need to access a sub-league (2. Bundesliga, LaLiga 2, etc.)
- ✅ The "Choose a tournament" dropdown is visible on a league page

## Limitations

- League headers must be **exact string matches** (e.g., "Spain. LaLiga 2" — NOT "Spain LaLiga 2")
- Some leagues may have no matches for the selected time filter
- Not all sections are expandable (pre-season, off-season leagues may be permanently empty)
