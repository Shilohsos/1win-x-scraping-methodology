"""
10x Betting — Injuries Collector
────────────────────────────────────────────────────────────────────────────────
Sources:
  - Sofascore Player Profile API (via proxied Chrome headless)
    → Use: scripts/epl_scanner.py or SofascoreInjuryScanner class below
  - API-Football (api-football.com) via RapidAPI (legacy, requires paid key)

Sofascore approach:
  Each player's profile on Sofascore has an optional 'injury' field containing:
    { reason, status (dayToDay/out/sidelined), expectedReturn, endDateTimestamp }

  To scan: get team squad from EPL season players endpoint, then fetch each
  player's profile to check for the injury field. Cached in memory.

  See scripts/epl_scanner.py for full CLI implementation.
"""
import logging
import aiohttp
import os
from datetime import datetime
from typing import List, Optional, Dict
from src.models.match import Match

logger = logging.getLogger("10xbet.injuries")

BASE_URL = "https://api-football-v1.p.rapidapi.com/v3"

class InjuryStatus:
    OK = "ok"          # Available
    DOUBT = "doubt"    # Questionable
    OUT = "out"        # Confirmed unavailable

class InjuryRecord:
    """Player injury information for a team"""
    def __init__(self, player_name: str, injury_type: str, status: str, return_date: Optional[str] = None):
        self.player_name = player_name
        self.injury_type = injury_type    # e.g. "Knee injury", "Hamstring"
        self.status = status              # "ok", "doubt", "out"
        self.return_date = return_date    # Expected return (YYYY-MM-DD) or None

class InjuriesCollector:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY", "")
        self.headers = {
            "x-apisports-key": self.api_key,
            "x-rapidapi-host": "api-football-v1.p.rapidapi.com"
        }
        self._cache: Dict[str, Dict] = {}   # key: f"{type}:{id}:{season}", value: list[InjuryRecord]
        self.cache_ttl_days = 1

    async def get_team_injuries(self, team_id: str, season: str) -> List[InjuryRecord]:
        """Fetch injury list for a specific team and season"""
        cache_key = f"team:{team_id}:{season}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        params = {"team": team_id, "season": season}
        records = await self._fetch_injuries(params)
        self._cache[cache_key] = records
        return records

    async def get_league_injuries(self, league_id: str, season: str) -> List[InjuryRecord]:
        """Fetch injury list for an entire league (batched)"""
        cache_key = f"league:{league_id}:{season}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        params = {"league": league_id, "season": season}
        records = await self._fetch_injuries(params)
        self._cache[cache_key] = records
        return records

    async def _fetch_injuries(self, params: dict) -> List[InjuryRecord]:
        url = f"{BASE_URL}/injuries"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=self.headers, params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._parse_injuries(data)
                    elif resp.status == 429:
                        logger.warning(f"API-Football rate limited (injuries): {resp.status}")
                    else:
                        logger.warning(f"API-Football error {resp.status} for injuries")
        except Exception as e:
            logger.error(f"Injuries fetch error: {e}")
        return []

    def _parse_injuries(self, data: dict) -> List[InjuryRecord]:
        records = []
        for item in data.get("response", []):
            player = item.get("player", {})
            team = item.get("team", {})
            injury = item.get("injury", {})
            # API-Football returns:
            #   player.name, injury.type, injury.start, injury.end
            record = InjuryRecord(
                player_name=player.get("name", "Unknown"),
                injury_type=injury.get("type", "Unknown"),
                status=self._classify_status(injury),
                return_date=injury.get("end")  # Expected recovery date
            )
            records.append(record)
        return records

    def _classify_status(self, injury: dict) -> str:
        """Map API-Football's injury data to our status enum"""
        if not injury:
            return InjuryStatus.OK
        # API doesn't provide status; presence of injury means OUT until return_date passes
        ret = injury.get("end", "")
        if ret:
            try:
                ret_dt = datetime.strptime(ret, "%Y-%m-%d")
                if ret_dt.date() < datetime.now().date():
                    return InjuryStatus.OK
            except ValueError:
                pass
        return InjuryStatus.OUT

    def _get_cached(self, cache_key: str) -> Optional[List[InjuryRecord]]:
        """Simple in-memory cache; TTL handled by stale-while-revalidate pattern"""
        entry = self._cache.get(cache_key)
        return entry if entry else None

    def summarize_team_injuries(self, team_id: str, season: str) -> Dict:
        """Return summary: {'available': n, 'doubt': n, 'out': n, 'critical_missing': int}"""
        records = asyncio.run(self.get_team_injuries(team_id, season)) if False else None  # placeholder
        # Will be filled after integration with async calling pattern
        raise NotImplementedError("Use get_team_injuries() directly")
