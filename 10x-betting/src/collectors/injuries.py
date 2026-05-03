"""
10x Betting — Injuries Collector
Source: Sofascore player profile API (via proxied browser)
Scope: Match-day squad only — checks only players in starting XI + subs

Flow:
  1. Fetch today's EPL matches → Sofascore event IDs
  2. For each match, fetch lineups → player IDs
  3. For each player in squad, fetch profile → check `injury` field
  4. Return list of injured players per team

Performance: ~35-40s per match (persistent browser, cached profiles)

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
    """Scans match-day squads for injured players via Sofascore."""

    def __init__(self):
        self.client = SofascoreClient()

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

        # Scheduled events (last 0-4 pages cover today)
        for page in range(5):
            ev = self.client.fetch(f"{API}/unique-tournament/{EPL_ID}/season/{SEASON_ID}/events/last/{page}")
            for e in ev.get("events", []):
                ts = e.get("startTimestamp", 0)
                if day_start <= ts < day_end and e["id"] not in seen:
                    seen.add(e["id"])
                    out.append(e)

        out.sort(key=lambda m: m.get("startTimestamp", 0))
        return out

    def get_lineups(self, match_id: int) -> Tuple[List[int], List[int]]:
        """
        Fetch lineups for a match.
        Returns (home_player_ids, away_player_ids).
        Empty lists if lineups not published.
        """
        lu = self.client.fetch(f"{API}/event/{match_id}/lineups")
        if "error" in lu or not lu:
            return [], []

        def _ids(side: str) -> List[int]:
            return [
                p.get("player", {}).get("id")
                for p in lu.get(side, {}).get("players", [])
                if p.get("player", {}).get("id")
            ]

        return _ids("home"), _ids("away")

    # ── Injury scan ────────────────────────────────────────────────

    def scan_match_squads(self, match_id: int) -> Dict[str, List[dict]]:
        """Scan both teams' match-day squads for injuries.

        Returns:
            {"home": [{"player": "...", "injury": "...", "status": "...", "return_date": "..."}],
             "away": [...]}
        """
        match_info = self.client.fetch(f"{API}/event/{match_id}")
        ev = match_info.get("event", {})
        home_team = ev.get("homeTeam", {}).get("name", "Home")
        away_team = ev.get("awayTeam", {}).get("name", "Away")

        home_pids, away_pids = self.get_lineups(match_id)

        logger.info("  %s: scanning %d players", home_team, len(home_pids))
        home_inj = self._scan_players(home_pids)

        logger.info("  %s: scanning %d players", away_team, len(away_pids))
        away_inj = self._scan_players(away_pids)

        result = {"home": home_inj, "away": away_inj}
        self._log_result(home_team, home_inj)
        self._log_result(away_team, away_inj)
        return result

    def scan_today(self) -> Dict[int, Dict[str, List[dict]]]:
        """Scan all today's EPL matches. Returns {match_id: {home: [...], away: [...]}}."""
        matches = self.today_matches()
        logger.info("Scanning %d EPL matches for injuries...", len(matches))
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
