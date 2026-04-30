"""10x Betting — Fixtures Collector
Source: Football-Data.org (free, no key needed for basic access)
Correct competition codes (Football-Data.org):
  PL = English Premier League
  CL = UEFA Champions League
  PD = Primera Division (La Liga)
"""
import logging
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from src.models.match import Match

logger = logging.getLogger("10xbet.fixtures")

BASE_URL = "https://api.football-data.org/v4"

# Correct Football-Data.org competition codes
LEAGUE_CODES = {
    "PL": "PL",   # English Premier League
    "CL": "CL",   # UEFA Champions League
    "PD": "PD",   # Primera Division (La Liga)
}

# Approximate venue coordinates for weather lookups
VENUE_COORDS = {
    "PL": {"latitude": 52.0, "longitude": -1.0},      # England centroid
    "CL": {"latitude": 50.0, "longitude": 10.0},      # Central Europe
    "PD": {"latitude": 40.42, "longitude": -3.70},    # Spain centroid
}

class FixturesCollector:
    def __init__(self, api_key: Optional[str] = None):
        # Football-Data.org works without a key on free tier (rate limited)
        # Providing a key raises rate limits significantly
        self.headers = {}
        if api_key:
            self.headers["X-Auth-Token"] = api_key

    async def fetch_upcoming(
        self, league_ids: List[str], hours_ahead: int = 48
    ) -> List[Match]:
        matches = []
        for league_id in league_ids:
            code = LEAGUE_CODES.get(league_id)
            if not code:
                logger.warning(f"Unknown league_id: {league_id}")
                continue
            fetched = await self._fetch_league(league_id, code, hours_ahead)
            matches.extend(fetched)
        logger.info(f"Fixtures: fetched {len(matches)} upcoming matches")
        return matches

    async def _fetch_league(
        self, league_id: str, code: str, hours_ahead: int
    ) -> List[Match]:
        url = f"{BASE_URL}/competitions/{code}/matches"
        params = {"status": "SCHEDULED"}
        matches = []
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        cutoff = datetime.now(timezone.utc) + timedelta(
                            hours=hours_ahead
                        )
                        coords = VENUE_COORDS.get(code, {})
                        for m in data.get("matches", []):
                            utc_str = m.get("utcDate", "")
                            try:
                                kickoff = datetime.fromisoformat(
                                    utc_str.replace("Z", "+00:00")
                                )
                            except (ValueError, AttributeError):
                                continue
                            if kickoff > cutoff:
                                continue
                            referee = m.get("referees", [])
                            referee_id = (
                                str(referee[0].get("id", ""))
                                if referee else ""
                            )
                            match = Match(
                                id=str(m.get("id", "")),
                                home_team=m.get("homeTeam", {}).get(
                                    "name", "Unknown"
                                ),
                                away_team=m.get("awayTeam", {}).get(
                                    "name", "Unknown"
                                ),
                                league=league_id,
                                venue=m.get("venue", "Unknown"),
                                kickoff=kickoff,
                                referee_id=referee_id,
                                latitude=coords.get("latitude"),
                                longitude=coords.get("longitude"),
                            )
                            matches.append(match)
                    elif resp.status == 429:
                        logger.warning(
                            f"Rate limited by Football-Data.org for {code}"
                        )
                    else:
                        logger.error(
                            f"Football-Data.org returned {resp.status} for {code}"
                        )
        except Exception as e:
            logger.error(f"Fixtures fetch error for {code}: {e}")
        return matches
