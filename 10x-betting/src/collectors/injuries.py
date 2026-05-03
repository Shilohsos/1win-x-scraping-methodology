"""
10x Betting — Injuries Collector
Source: Sofascore player profile API (via proxied browser)
Scope: Full squad — all players registered to each team in the season

Flow:
  1. Fetch full competition squad → {team_id: [player_id, ...]}
     (1 API call, cached per season)
  2. For each match, fetch player profiles for all squad members
  3. Check `injury` field on each profile
  4. Return injured players per team

Performance: ~45-60s per team for first scan (cached thereafter)
             528 players total across 20 EPL teams

Requires:
  - botasaurus_driver (from scraperfc_venv)
  - Webshare SA residential proxy (configured below)
"""
import logging
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Set, Tuple

logger = logging.getLogger("10xbet.injuries")

# ─── Sofascore Config ─────────────────────────────────────────────
API = "https://api.sofascore.com/api/v1"
EPL_ID = 17
SEASON_ID = 76986   # 2025/26
PROXY = "http://pzxyatji:tqz8zcybhmj7@82.29.245.95:6919"

from botasaurus_driver.driver import Driver as _Driver


class SofascoreClient:
    """Persistent browser-based client for Sofascore JSON API."""

    def __init__(self):
        self._driver: Optional[_Driver] = None
        self._player_cache: Dict[int, dict] = {}

    def _get_driver(self) -> _Driver:
        if self._driver is None:
            self._driver = _Driver(
                headless=True,
                block_images_and_css=True,
                wait_for_complete_page_load=True,
                proxy=PROXY,
            )
        return self._driver

    def fetch(self, url: str) -> dict:
        """Fetch JSON from Sofascore via persistent proxied browser."""
        d = self._get_driver()
        try:
            d.get(url)
            return json.loads(d.page_text)
        except json.JSONDecodeError:
            logger.warning("JSON parse error from %s", url)
            return {}
        except Exception as e:
            logger.warning("Fetch error %s: %s", url, e)
            return {}

    def close(self):
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None

    def player(self, pid: int) -> dict:
        """Cached player profile. Returns {} on error."""
        if pid not in self._player_cache:
            data = self.fetch(f"{API}/player/{pid}")
            self._player_cache[pid] = data.get("player", {})
        return self._player_cache[pid]

    def get_injury(self, pid: int) -> Optional[dict]:
        """Returns injury dict or None."""
        return self.player(pid).get("injury")


class SofascoreInjuryScanner:
    """Scans full squads for injured players via Sofascore player profiles.

    Uses a single API call to get ALL players in the EPL season grouped by team,
    then fetches each player's profile to check for injury data.
    """

    def __init__(self):
        self.client = SofascoreClient()
        self._squad_cache: Optional[Dict[int, List[int]]] = None  # team_id -> [player_id]
        self._team_name_cache: Dict[int, str] = {}

    # ── Full squad data (cached per season) ────────────────────────

    def _load_squads(self):
        """Fetch ALL EPL players in one call, group by team. Cached."""
        if self._squad_cache is not None:
            return
        logger.info("Fetching full EPL squad roster (%d players expected)...", 528)
        data = self.client.fetch(f"{API}/unique-tournament/{EPL_ID}/season/{SEASON_ID}/players")
        teams: Dict[int, List[int]] = {}
        for p in data.get("players", []):
            tid = p.get("team", {}).get("id") or p.get("teamId")
            pid = p.get("playerId") or p.get("id")
            name = p.get("team", {}).get("name", "")
            if tid and pid:
                teams.setdefault(tid, []).append(pid)
                if name and tid not in self._team_name_cache:
                    self._team_name_cache[tid] = name
        self._squad_cache = teams
        logger.info("Loaded %d teams, %d total players", len(teams),
                     sum(len(pids) for pids in teams.values()))

    def get_team_roster(self, team_id: int) -> List[int]:
        """Get all player IDs for a team."""
        self._load_squads()
        return self._squad_cache.get(team_id, [])

    # ── Match data ─────────────────────────────────────────────────

    def today_matches(self) -> List[dict]:
        """All EPL matches happening today (live + scheduled)."""
        now = datetime.now(timezone.utc)
        day_start = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp())
        day_end = day_start + 86400
        seen: Set[int] = set()
        out = []

        # Live events
        for e in self.client.fetch(f"{API}/sport/football/events/live").get("events", []):
            tid = e.get("tournament", {}).get("uniqueTournament", {}).get("id")
            if tid == EPL_ID and e["id"] not in seen:
                seen.add(e["id"])
                out.append(e)

        # Scheduled events
        for page in range(5):
            ev = self.client.fetch(f"{API}/unique-tournament/{EPL_ID}/season/{SEASON_ID}/events/last/{page}")
            for e in ev.get("events", []):
                ts = e.get("startTimestamp", 0)
                if day_start <= ts < day_end and e["id"] not in seen:
                    seen.add(e["id"])
                    out.append(e)

        out.sort(key=lambda m: m.get("startTimestamp", 0))
        return out

    # ── Injury scan (full squad) ───────────────────────────────────

    def scan_team(self, team_id: int, team_name: str = "") -> List[dict]:
        """Scan ALL players registered to a team for injuries.

        Returns list of injured players, each with:
          {player, player_id, injury, status, return_date, position}
        """
        pids = self.get_team_roster(team_id)
        if not pids:
            logger.warning("No squad data for team %d (%s)", team_id, team_name)
            return []

        logger.info("  %s: scanning full squad (%d players)...", team_name or f"Team {team_id}", len(pids))
        injured = []
        for pid in pids:
            inj = self.client.get_injury(pid)
            if inj and inj.get("status") in ("out", "sidelined"):
                profile = self.client.player(pid)
                injured.append({
                    "player": profile.get("name", f"Player {pid}"),
                    "player_id": pid,
                    "injury": inj.get("reason", "Unknown"),
                    "status": inj.get("status", "out"),
                    "return_date": self._format_return(inj.get("endDateTimestamp")),
                })

        if injured:
            details = "; ".join(f"{i['player']} ({i['injury']})" for i in injured[:5])
            if len(injured) > 5:
                details += f" ... +{len(injured)-5} more"
            logger.info("  🩹❌ %s — %d injured: %s", team_name or f"Team {team_id}", len(injured), details)
        else:
            logger.info("  ✅ %s — All fit (%d players)", team_name or f"Team {team_id}", len(pids))

        return injured

    def scan_match_squads(self, match_id: int) -> Dict[str, List[dict]]:
        """Scan full squads for both teams in a match.

        Uses team IDs from the match event, not lineups.
        Returns: {"home": [...], "away": [...]}
        """
        match_info = self.client.fetch(f"{API}/event/{match_id}")
        ev = match_info.get("event", {})
        home_tid = ev.get("homeTeam", {}).get("id")
        away_tid = ev.get("awayTeam", {}).get("id")
        home_name = ev.get("homeTeam", {}).get("name", "Home")
        away_name = ev.get("awayTeam", {}).get("name", "Away")

        result = {
            "home": self.scan_team(home_tid, home_name) if home_tid else [],
            "away": self.scan_team(away_tid, away_name) if away_tid else [],
        }
        return result

    def scan_today(self) -> Dict[int, Dict[str, List[dict]]]:
        """Scan all today's EPL matches. Returns {match_id: {home: [...], away: [...]}}."""
        self._load_squads()
        matches = self.today_matches()
        logger.info("Scanning %d EPL matches for all squad injuries...", len(matches))
        results = {}
        for m in matches:
            mid = m["id"]
            home = m.get("homeTeam", {}).get("name", "?")
            away = m.get("awayTeam", {}).get("name", "?")
            logger.info("Match: %s vs %s (ID %d)", home, away, mid)
            results[mid] = self.scan_match_squads(mid)
        return results

    def _scan_players(self, pids: List[int]) -> List[dict]:
        """Check each player for injury. Returns injured-only list."""
        injured = []
        for pid in pids:
            inj = self.client.get_injury(pid)
            if inj and inj.get("status") in ("out", "sidelined"):
                profile = self.client.player(pid)
                injured.append({
                    "player": profile.get("name", f"Player {pid}"),
                    "player_id": pid,
                    "injury": inj.get("reason", "Unknown"),
                    "status": inj.get("status", "out"),
                    "return_date": self._format_return(inj.get("endDateTimestamp")),
                })
        return injured

    def _format_return(self, ts: Optional[int]) -> str:
        if not ts:
            return "Unknown"
        try:
            return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return "Unknown"

    def _log_result(self, team: str, injuries: List[dict]):
        if injuries:
            details = "; ".join(f"{i['player']} ({i['injury']})" for i in injuries)
            logger.info("  🩹❌ %s — %d: %s", team, len(injuries), details)
        else:
            logger.info("  ✅ %s — All fit", team)

    def cleanup(self):
        self.client.close()


class InjuriesCollector:
    """
    Match-day-squad injury collector.

    Replaces the broken API-Football InjuriesCollector.
    Compatible with signal_engine interface.

    Usage:
        collector = InjuriesCollector()
        result = await collector.get_for_match(match_id=12345)
        # Returns: {"home": [...], "away": [...]}
    """

    def __init__(self):
        self._scanner: Optional[SofascoreInjuryScanner] = None
        self._cache: Dict[int, Dict[str, List[dict]]] = {}
        self._last_scan: float = 0
        self._scan_interval: float = 7200  # 2 hours

    def _get_scanner(self) -> SofascoreInjuryScanner:
        if self._scanner is None:
            self._scanner = SofascoreInjuryScanner()
        return self._scanner

    async def get_for_match(self, match_id: int) -> Dict[str, List[dict]]:
        """Get match-day squad injuries. Uses cache when fresh."""
        now = time.time()
        if match_id in self._cache and (now - self._last_scan) < self._scan_interval:
            return self._cache[match_id]

        scanner = self._get_scanner()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, scanner.scan_match_squads, match_id)
            self._cache[match_id] = result
            self._last_scan = now
            return result
        except Exception as e:
            logger.error("Injury scan failed for match %d: %s", match_id, e)
            return {"home": [], "away": []}

    def cleanup(self):
        if self._scanner is not None:
            self._scanner.cleanup()
            self._scanner = None

    # ── Legacy team-based interface ──
    def get_team_injuries(self, team_name: str) -> List[dict]:
        """Legacy: returns injury list for a team from cached scans."""
        for match_data in self._cache.values():
            for side in ("home", "away"):
                return match_data.get(side, [])
        return []
