import asyncio
import logging
import re
import unicodedata
import requests
from typing import Optional, Dict

logger = logging.getLogger("10xbet.odds")


# SportyBet API config
BASE_URL = "https://www.sportybet.com"
API_ENDPOINT = "/api/ng/factsCenter/pcUpcomingEvents"

# SportyBet market IDs → internal keys
# 1  = 1X2 (home/draw/away)
# 18 = Over/Under (multiple lines)
# 29 = GG/NG (both teams to score)
# Additional markets available: 10 (Asian Handicap), 11 (Correct Score), etc.
MARKET_MAP = {
    "1": "1x2",
    "18": "over_under",
    "29": "btts",
}

# ─── Team name normalization for SportyBet ↔ Football-Data matching ────
def _normalize_team_name(name: str) -> str:
    """
    Convert team name to a canonical form: lowercase, accent-stripped,
    punctuation removed, common club tokens (FC, AFC, CF, UD, etc.) dropped.
    """
    # Lowercase
    name = name.lower()
    # Strip accents/diacritics
    name = unicodedata.normalize('NFD', name)
    name = ''.join(ch for ch in name if unicodedata.category(ch) != 'Mn')
    # Remove punctuation symbols, keep alphanumerics and spaces
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    # Drop common suffixes/prefixes that appear in Football-Data names
    skip = {"fc", "afc", "cf", "ud", "cd", "ca", "rc", "rcd", "sc"}
    words = [w for w in name.split() if w not in skip]
    return " ".join(words).strip()

# Football-Data → SportyBet alias mapping (normalized → normalized)
TEAM_ALIAS: dict[str, str] = {
    "afc bournemouth": "bournemouth",
    "arsenal fc": "arsenal",
    "aston villa fc": "aston villa",
    "athletic club": "athletic bilbao",
    "brentford fc": "brentford",
    "brighton hove albion": "brighton",
    "burnley fc": "burnley",
    "ca osasuna": "osasuna",
    "chelsea fc": "chelsea",
    "club atletico de madrid": "atletico madrid",
    "crystal palace fc": "crystal palace",
    "deportivo alaves": "alaves",
    "elche cf": "elche cf",
    "everton fc": "everton",
    "fc barcelona": "barcelona",
    "fulham fc": "fulham",
    "getafe cf": "getafe",
    "girona fc": "girona",
    "leeds united fc": "leeds united",
    "levante ud": "levante",
    "liverpool fc": "liverpool",
    "manchester city": "man city",
    "manchester united": "man utd",
    "newcastle united": "newcastle",
    "nottingham forest fc": "nottingham forest",
    "rc celta de vigo": "celta",
    "rcd espanyol de barcelona": "espanyol",
    "rcd mallorca": "mallorca",
    "rayo vallecano de madrid": "rayo vallecano",
    "real betis balompie": "betis",
    "real madrid cf": "real madrid",
    "real oviedo": "real oviedo",
    "real sociedad de futbol": "real sociedad",
    "sevilla fc": "sevilla",
    "sunderland afc": "sunderland afc",
    "tottenham hotspur": "tottenham",
    "valencia cf": "valencia",
    "villarreal cf": "villarreal",
    "west ham united": "west ham",
    "wolverhampton wanderers": "wolves",
}


# Mobile user-agent required for correct content
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Infinix X6816D) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/112.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sportybet.com/ng/",
    "Origin": "https://www.sportybet.com",
    "X-Requested-With": "XMLHttpRequest",
}


class OddsCollector:
    """
    SportyBet Nigeria odds collector.
    Uses the public JSON API (pcUpcomingEvents) to fetch 1X2 and Over/Under markets.
    No authentication required.
    """

    def __init__(self, config=None, username=None, password=None, headless=True):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        logger.info("OddsCollector initialised (SportyBet HTTP API)")

    async def start(self):
        logger.info("OddsCollector started (HTTP client)")

    async def stop(self):
        logger.info("OddsCollector stopped")

    async def login(self) -> bool:
        logger.info("No login required (public API)")
        return True

    async def get_match_odds(self, match):
        return await self.get_odds(match.home_team, match.away_team)

    async def get_odds(self, home_team: str, away_team: str,
                       match_date: str = None) -> Dict:
        """
        Fetch odds for a match from SportyBet Nigeria API.
        Returns empty dict if match not found or API fails.
        """
        try:
            params = {
                "sportId": "sr:sport:1",
                # Request all relevant football markets
                "marketId": "1,18,10,29,11,26,36,14,60100",
                "pageSize": 100,
                "pageNum": 1,
                "option": 1,
            }
            r = self.session.get(
                BASE_URL + API_ENDPOINT,
                params=params,
                timeout=20
            )
            if r.status_code != 200:
                logger.warning(f"SportyBet API {r.status_code}: {r.text[:200]}")
                return {}

            payload = r.json()
            tournaments = payload.get("data", {}).get("tournaments", [])

            # Normalize fixture team names and resolve alias to SportyBet equivalents
            fh = _normalize_team_name(home_team)
            fa = _normalize_team_name(away_team)
            fh = TEAM_ALIAS.get(fh, fh)
            fa = TEAM_ALIAS.get(fa, fa)

            for tourney in tournaments:
                for ev in tourney.get("events", []):
                    sh = _normalize_team_name(ev.get("homeTeamName", ""))
                    sa = _normalize_team_name(ev.get("awayTeamName", ""))
                    if fh == sh and fa == sa:
                        return self._parse_event(ev)

            logger.warning(f"No SportyBet match: {home_team} vs {away_team}")
            return {}

        except Exception as e:
            logger.error(f"SportyBet fetch error: {e}")
            return {}

    def _parse_event(self, ev: Dict) -> Dict:
        """Parse event JSON into normalized odds dict."""
        result = {"meta": {"sportybet_event_id": ev.get("eventId")}}
        markets = ev.get("markets", [])

        # 1X2 (market id "1")
        for m in markets:
            mid = str(m.get("id", ""))
            if mid == "1":
                for o in m.get("outcomes", []):
                    oid = str(o.get("id", ""))
                    if oid == "1":   # Home
                        result["home"] = self._parse_odds(o.get("odds"))
                    elif oid == "2": # Draw
                        result["draw"] = self._parse_odds(o.get("odds"))
                    elif oid == "3": # Away
                        result["away"] = self._parse_odds(o.get("odds"))

        # Over/Under (market id "18") – return multiple lines
        over_under = {}
        for m in markets:
            if str(m.get("id","")) == "18":
                for o in m.get("outcomes", []):
                    oid = str(o.get("id", ""))
                    odds = self._parse_odds(o.get("odds"))
                    if not odds:
                        continue
                    # outcome desc like "Over 2.5" or "Under 2.5"
                    desc = o.get("desc", "").lower()
                    if "over" in desc:
                        # extract line number
                        import re
                        m_line = re.search(r"over\s+([\d.]+)", desc)
                        if m_line:
                            line = float(m_line.group(1))
                            over_under[f"over_{line}"] = odds
                    elif "under" in desc:
                        m_line = re.search(r"under\s+([\d.]+)", desc)
                        if m_line:
                            line = float(m_line.group(1))
                            over_under[f"under_{line}"] = odds
        # Flatten: separate entry for each line
        for k, v in over_under.items():
            result[k] = v

        # Optionally include GG/NG (market id "29")
        for m in markets:
            if str(m.get("id","")) == "29":
                for o in m.get("outcomes", []):
                    desc = o.get("desc","").lower()
                    odds = self._parse_odds(o.get("odds"))
                    if "yes" in desc:
                        result["btts_yes"] = odds
                    elif "no" in desc:
                        result["btts_no"] = odds

        return result

    @staticmethod
    def _parse_odds(raw) -> Optional[float]:
        """Convert odds string to float, validate range."""
        try:
            val = float(str(raw).replace(",", "."))
            return val if 1.0 < val < 1000 else None
        except (TypeError, ValueError):
            return None
