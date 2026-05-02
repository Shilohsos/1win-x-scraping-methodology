# Finding: Three-Tier Page Structure

**Date Discovered:** 2026-05-02  
**Method:** Live validation across multiple page endpoints

---

| Tier | URL Pattern | Purpose | Completeness |
|------|-------------|---------|--------------|
| **Tier 1 — Main** | `https://1win.ng/betting` | Curated highlights carousel | ✗ Partial — ~5 fixtures/league, early kickoffs only |
| **Tier 2 — Aggregated** | `/betting/prematch/soccer-18?time=1d` | All soccer leagues in one view | ✓ Full for most leagues |
| **Tier 3 — Dedicated** | `/betting/prematch/soccer-18/{slug}-{id}?time=1d` | Single-league full fixture list | ✓ Most reliable |

## Critical Finding

The main `/betting` page **omits later fixtures**. Example from Bundesliga on May 2:
- Main page: only 5 matches (all 15:30 kickoffs)
- Dedicated page: 6 matches (includes 18:30 Leverkusen vs Leipzig)

**Rule:** If you see only 5–6 fixtures in a major European league (expected 9–10), you are on an incomplete route. Switch to dedicated or aggregated URL immediately.

## URL Selection Priority
1. Dedicated league URL (if slug+ID known)
2. Aggregated soccer page
3. Main /betting page (incomplete — sanity check only)
