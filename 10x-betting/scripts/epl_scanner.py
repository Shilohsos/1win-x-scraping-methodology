"""
EPL Match Scanner — Sofascore Player Profile Injury Detection
================================================================================
Scrapes live/upcoming EPL matches, full lineups, and injury data from
Sofascore's player profile API endpoint.

Performance: ~90-180s for full matchday scan (2 matches).
Caches player profiles to avoid redundant fetches.

Usage:
  /root/scraperfc_venv/bin/python scripts/epl_scanner.py
  /root/scraperfc_venv/bin/python scripts/epl_scanner.py --team "Liverpool FC"
  /root/scraperfc_venv/bin/python scripts/epl_scanner.py --json
  /root/scraperfc_venv/bin/python scripts/epl_scanner.py --lineups-only

Requires:
  - ScraperFC (botasaurus) with Chrome
  - Webshare residential proxy (configured below)
  - Google Chrome --no-sandbox wrapper (/opt/google/chrome/google-chrome)
"""

import sys
import json
import time
import argparse
from datetime import datetime, timezone
from typing import Optional
sys.stdout.reconfigure(line_buffering=True)

# ─── Configuration ───────────────────────────────────────────────────────────
PROXY = "http://pzxyatji:tqz8zcybhmj7@82.29.245.95:6919"
API = "https://api.sofascore.com/api/v1"
EPL_ID = 17
SEASON_ID = 76986  # 25/26

EPL_TEAMS = {
    35: "Manchester United", 44: "Liverpool FC", 42: "Arsenal",
    38: "Chelsea", 17: "Manchester City", 33: "Tottenham",
    39: "Newcastle United", 40: "Aston Villa", 37: "West Ham",
    211: "Brighton", 7537: "Brentford", 43: "Fulham",
    7: "Crystal Palace", 3: "Wolverhampton", 48: "Everton",
    14: "Nottingham Forest", 31: "Leicester City", 32: "Ipswich Town",
    45: "Southampton", 46: "Leeds United", 103: "Bournemouth",
}
TEAM_ID_BY_NAME = {v: k for k, v in EPL_TEAMS.items()}

# ─── Proxied Browser ─────────────────────────────────────────────────────────
from botasaurus_driver.driver import Driver as _Driver

_cache = {}  # pid -> player dict

def fetch(url: str) -> dict:
    d = _Driver(headless=True, block_images_and_css=True,
                wait_for_complete_page_load=True, proxy=PROXY)
    try:
        d.get(url)
        return json.loads(d.page_text)
    except json.JSONDecodeError:
        return {}
    finally:
        try:
            d.close()
        except Exception:
            pass

def player(pid: int) -> dict:
    """Cached player profile. Returns {} on error."""
    if pid not in _cache:
        p = fetch(f"{API}/player/{pid}")
        _cache[pid] = p.get("player", {})
    return _cache[pid]

# ─── Data ────────────────────────────────────────────────────────────────────

def today_matches():
    """All EPL matches happening today (live + scheduled)."""
    now = datetime.now(timezone.utc)
    ds = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp())
    de = ds + 86400
    seen, out = set(), []

    live = fetch(f"{API}/sport/football/events/live")
    for e in live.get("events", []):
        if e.get("tournament", {}).get("uniqueTournament", {}).get("id") == EPL_ID:
            if e["id"] not in seen:
                seen.add(e["id"]); out.append(e)

    for p in range(5):
        ev = fetch(f"{API}/unique-tournament/{EPL_ID}/season/{SEASON_ID}/events/last/{p}")
        for e in ev.get("events", []):
            ts = e.get("startTimestamp", 0)
            if ds <= ts < de and e["id"] not in seen:
                seen.add(e["id"]); out.append(e)

    out.sort(key=lambda m: m.get("startTimestamp", 0))
    return out

def lineups(mid: int):
    """Return (home_starters, home_subs, away_starters, away_subs) dict lists."""
    lu = fetch(f"{API}/event/{mid}/lineups")
    if "error" in lu:
        return [], [], [], []

    def _ps(arr):
        return [{
            "pid": p.get("player", {}).get("id"),
            "name": p.get("player", {}).get("name", "?"),
            "shirt": p.get("shirtNumber", ""),
            "pos": p.get("position", ""),
        } for p in arr]

    h_s = _ps(lu.get("home", {}).get("players", []))
    a_s = _ps(lu.get("away", {}).get("players", []))
    h_start = [p for p in h_s if not any(s.get("pid") == p["pid"] for s in (a_s or []))]
    h_subs = []
    a_subs = []

    # Sub separation
    if "home" in lu:
        h_subs = _ps([p for p in lu["home"].get("players", []) if p.get("substitute")])
    if "away" in lu:
        a_subs = _ps([p for p in lu["away"].get("players", []) if p.get("substitute")])

    # Re-split correctly
    h_start = _ps([p for p in lu.get("home", {}).get("players", []) if not p.get("substitute")])
    h_subs = _ps([p for p in lu.get("home", {}).get("players", []) if p.get("substitute")])
    a_start = _ps([p for p in lu.get("away", {}).get("players", []) if not p.get("substitute")])
    a_subs = _ps([p for p in lu.get("away", {}).get("players", []) if p.get("substitute")])
    return h_start, h_subs, a_start, a_subs

def squad_by_team():
    """Return {team_id: [player_id]} for all EPL teams. 1 API call."""
    r = fetch(f"{API}/unique-tournament/{EPL_ID}/season/{SEASON_ID}/players")
    teams = {}
    for p in r.get("players", []):
        tid = p.get("team", {}).get("id") or p.get("teamId")
        pid = p.get("playerId") or p.get("id")
        if tid and pid:
            teams.setdefault(tid, []).append(pid)
    return teams

def season_squad(tid: int):
    """Player IDs for a team, from season cache."""
    if not hasattr(season_squad, "_cache"):
        season_squad._cache = squad_by_team()
    return season_squad._cache.get(tid, [])

# ─── Output ──────────────────────────────────────────────────────────────────

def inj_str(inj: Optional[dict]) -> str:
    if not inj: return ""
    r = inj.get("reason", "?")
    s = inj.get("status", "?")
    end = inj.get("endDateTimestamp")
    ret = f" [~{datetime.fromtimestamp(end, timezone.utc).strftime('%d %b')}]" if end else ""
    icon = "🩹❌" if s in ("out", "sidelined") else "🩹⚠️"
    return f"  {icon} {r} ({s}){ret}"

def fmt_line(p, inj=None):
    s = f"  {p['name']}"
    if p.get("shirt"): s = f"  #{p['shirt']} {p['name']}"
    if p.get("pos"): s += f" ({p['pos']})"
    if inj: s += inj_str(inj)
    return s

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="EPL Scanner (Sofascore Injuries)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--team", type=str, help="Single team scan")
    ap.add_argument("--lineups-only", action="store_true", help="Skip squad injury check")
    ap.add_argument("--progress", action="store_true", help="Show progress dots")
    args = ap.parse_args()

    if args.team:
        tid = TEAM_ID_BY_NAME.get(args.team)
        if not tid:
            print(f"Unknown team. Options: {', '.join(sorted(TEAM_ID_BY_NAME))}")
            sys.exit(1)
        squad = season_squad(tid)
        out_i, out_p, out_f = [], [], []
        for pid in squad:
            p = player(pid)
            if not p.get("name"): continue
            n = p["name"]
            i = p.get("injury")
            if i:
                (out_p if i.get("status") in ("out", "sidelined") else out_i).append((n, i))
            else:
                out_f.append(n)
        if args.json:
            print(json.dumps({"team": args.team, "injured_out": [{"n": n, "i": i} for n, i in out_p], "playing_through": [{"n": n, "i": i} for n, i in out_i], "fit": out_f}, indent=2))
        else:
            print(f"\n{'='*55}\n  {args.team.upper()} — INJURY REPORT\n{'='*55}")
            print(f"\n  🩹❌ INJURED & OUT ({len(out_p)}):")
            for n, i in out_p: print(f"    • {n} — {i.get('reason','?')}{inj_str(i)}")
            print(f"\n  🩹⚠️ PLAYING THROUGH ({len(out_i)}):")
            for n, i in out_i: print(f"    • {n}{inj_str(i)}")
            print(f"\n  ✅ FIT ({len(out_f)}):")
            for n in out_f: print(f"    • {n}")
        return

    # Matchday
    print("Fetching EPL matches...", end="", flush=True)
    matches = today_matches()
    print(f" {len(matches)} found")

    if args.json:
        out = {"matches": [], "ts": datetime.now(timezone.utc).isoformat()}
        for m in matches:
            h1, h2, a1, a2 = lineups(m["id"])
            for arr in [h1, h2, a1, a2]:
                for p in arr:
                    p["injury"] = player(p["pid"]).get("injury")
            out["matches"].append({
                "id": m["id"], "home": m.get("homeTeam",{}).get("name"), "away": m.get("awayTeam",{}).get("name"),
                "home_start": h1, "home_subs": h2, "away_start": a1, "away_subs": a2
            })
        print(json.dumps(out, indent=2))
        return

    for m in matches:
        mid = m["id"]
        home = m.get("homeTeam", {}).get("name", "?")
        away = m.get("awayTeam", {}).get("name", "?")
        hid = m.get("homeTeam", {}).get("id")
        aid = m.get("awayTeam", {}).get("id")
        sc = m.get("status", {}).get("code", 0)
        st = m.get("status", {}).get("type", "?")
        dt = datetime.fromtimestamp(m.get("startTimestamp", 0), timezone.utc)
        hs = m.get("homeScore", {}).get("current", "")
        as_ = m.get("awayScore", {}).get("current", "")
        score = f"{hs} - {as_}" if hs else "vs"
        icons = {0: "⏳", 6: "▶️", 7: "▶️", 10: "⏸️", 100: "✅"}
        ti = f" ({m.get('status',{}).get('description','')})" if st == "inprogress" else f" — {dt.strftime('%H:%M')} UTC"

        print(f"\n{'─'*50}\n  {home} vs {away}  {score}  {icons.get(sc,'❓')}{ti}\n{'─'*50}")

        h1, h2, a1, a2 = lineups(mid)
        all_lu = h1 + h2 + a1 + a2

        for team_n, start, subs in [(home, h1, h2), (away, a1, a2)]:
            print(f"\n  ⬜ {team_n} ({len(start)} + {len(subs)}):")
            for p in start:
                i = player(p["pid"]).get("injury")
                print(f"    #{p['shirt']} {p['name']} ({p['pos']})" + (inj_str(i) if i else ""))
            if subs:
                print("    ── Bench ──")
                for p in subs:
                    i = player(p["pid"]).get("injury")
                    print(f"    🔁 #{p['shirt']} {p['name']} ({p['pos']})" + (inj_str(i) if i else ""))

        if not args.lineups_only:
            lu_ids = {p["pid"] for p in all_lu}
            for team_n, tid in [(home, hid), (away, aid)]:
                if not tid: continue
                squad = season_squad(tid)
                missing = [pid for pid in squad if pid not in lu_ids]
                out_p, out_i = [], []
                for pid in missing:
                    p = player(pid)
                    if not p.get("name"): continue
                    inj = p.get("injury")
                    if inj:
                        (out_p if inj.get("status") in ("out", "sidelined") else out_i).append((p["name"], inj))
                if out_p:
                    print(f"\n  🩹❌ {team_n} — INJURED & OUT ({len(out_p)}):")
                    for n, i in out_p: print(f"    • {n} — {i.get('reason','?')}{inj_str(i)}")
                if out_i:
                    print(f"  🩹⚠️ {team_n} — PLAYING THROUGH ({len(out_i)}):")
                    for n, i in out_i: print(f"    • {n}{inj_str(i)}")

    print(f"\n{'='*55}\n  ✅ {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}\n{'='*55}")

if __name__ == "__main__":
    main()
