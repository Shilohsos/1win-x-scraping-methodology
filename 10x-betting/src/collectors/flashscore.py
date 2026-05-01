import logging
import requests
import time
import re
import json
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger("10xbet.flashscore")

_TEAM_MAP: Dict[str, int] = {}
_LAST_REFRESH = 0

import os
from pathlib import Path
ENV_PATH = Path('/root/10x-betting/.env')
if ENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(str(ENV_PATH))
API_KEY = os.getenv('FOOTBALL_DATA_API_KEY')
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY} if API_KEY else {}

CACHE_PATH = Path("/root/10x-betting/.cache/fd_team_map.json")
_LAST_API_CALL = 0

# Competitions we cover: PL, CL, PD
COMP_CODES = ["PL", "CL", "PD"]

def _clean_name(name: str) -> str:
    n = name.lower()
    n = re.sub(r'[ééeè]', 'e', n)
    n = re.sub(r'[áaà]', 'a', n)
    n = re.sub(r'[íiì]', 'i', n)
    n = re.sub(r'[óoò]', 'o', n)
    n = re.sub(r'[úuù]', 'u', n)
    n = re.sub(r'[ñn]', 'n', n)
    n = re.sub(r'\b(fc|cdf|cf|cd|ud|rc|rcd|ca)\b', '', n)
    n = re.sub(r'\bde\b', '', n)
    n = re.sub(r'\bclub\b', '', n)
    n = re.sub(r'\bbalomp?ie\b', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def _refresh_team_map() -> bool:
    global _TEAM_MAP, _LAST_REFRESH
    if not API_KEY:
        logger.error("Flashscore: FOOTBALL_DATA_API_KEY missing from .env")
        return False
    try:
        _TEAM_MAP.clear()
        for code in COMP_CODES:
            r = requests.get(f"{BASE_URL}/competitions/{code}/teams",
                             headers=HEADERS, timeout=15)
            if r.status_code != 200:
                logger.warning("Failed to fetch %s teams: HTTP %s", code, r.status_code)
                continue
            teams = r.json().get('teams', [])
            for t in teams:
                tid = t['id']
                name = t['name']
                _TEAM_MAP[name.lower()] = tid
                _TEAM_MAP[_clean_name(name)] = tid
                if t.get('shortName'):
                    _TEAM_MAP[t['shortName'].lower()] = tid
            logger.info("Loaded %d teams from %s", len(teams), code)
        # Manual aliases for ambiguous/common names not guaranteed from API
        ALIASES = {
            # PL
            'manchester city': 57, 'man city': 57, 'mancity': 57,
            'manchester united': 66, 'man united': 66, 'manutd': 66,
            'liverpool': 64, 'lfc': 64,
            'chelsea': 61, 'cfc': 61,
            'arsenal': 56, 'afc': 56,
            'tottenham': 73, 'spurs': 73,
            'newcastle': 67, 'newcastle united': 67,
            'brighton': 397, 'brighton & hove albion': 397,
            'wolves': 76, 'wolverhampton': 76, 'wolverhampton wanderers': 76,
            'west ham': 563, 'west ham united': 563,
            'aston villa': 58, 'villa': 58,
            'crystal palace': 354, 'palace': 354,
            'leeds': 341, 'leeds united': 341,
            'leicester': 62, 'leicester city': 62,
            'everton': 62,  # note: might overlap; verify
            'sunderland': 71,
            'burnley': 328,
            'brentford': 402,
            'nottingham forest': 351, 'forest': 351,
            'afc bournemouth': 1044, 'bournemouth': 1044,
            # CL (top clubs)
            'bayern': 5, 'bayern munich': 5,
            'dortmund': 4, 'borussia dortmund': 4,
            'psg': 524, 'paris saint-germain': 524,
            'inter': 108, 'internazionale': 108,
            'ac milan': 98, 'milan': 98,
            'juventus': 109,
            'bayer leverkusen': 2,
            'atlético madrid': 78, 'atletico': 78, 'atleti': 78,
            'porto': 122, 'fc porto': 122,
            'benfica': 190,
            # already mapped via API: barcelona, real madrid, valencia, sevilla, etc.
        }
        _TEAM_MAP.update(ALIASES)
        _LAST_REFRESH = time.time()
        logger.info("Flashscore team map ready — %d teams across %s",
                    len(_TEAM_MAP), ','.join(COMP_CODES))
        return True
    except Exception as e:
        logger.error("Failed to refresh team map: %s", e)
        return False

if not _TEAM_MAP:
    _refresh_team_map()

class FlashscoreCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}
        logger.info("FlashscoreCollector ready — using Football-Data.org API")

    def _get_team_id(self, team_name: str) -> Optional[int]:
        key = team_name.lower()
        if key in _TEAM_MAP:
            return _TEAM_MAP[key]
        cleaned = _clean_name(team_name)
        return _TEAM_MAP.get(cleaned)

    def get_team_form(self, team_name: str) -> Optional[dict]:
        _ensure_team_map()
        team_id = self._get_team_id(team_name)
        if not team_id:
            logger.warning("Flashscore: unknown team '%s'", team_name)
            return None
        url = f"{BASE_URL}/teams/{team_id}/matches"
        params = {"status": "FINISHED", "limit": 5}
        try:
            r = self.session.get(url, params=params, headers=HEADERS, timeout=15)
            if r.status_code == 429:
                logger.warning("Flashscore: rate-limited for %s (id=%s)", team_name, team_id)
                return {
                    "team_id": team_id, "form": "", "last_5": [],
                    "goals_scored_avg": 0.0, "goals_conceded_avg": 0.0,
                    "matches_analyzed": 0,
                }
            if r.status_code != 200:
                logger.error("Flashscore API error %s for %s", r.status_code, team_name)
                return None
            matches = r.json().get('matches', [])
            if not matches:
                return {
                    "team_id": team_id, "form": "", "last_5": [],
                    "goals_scored_avg": 0.0, "goals_conceded_avg": 0.0,
                    "matches_analyzed": 0,
                }
            outcomes = []
            gf_total = 0
            ga_total = 0
            for m in matches[:5]:
                home_id = m['homeTeam']['id']
                is_home = (home_id == team_id)
                home_ft = m['score']['fullTime']['home'] or 0
                away_ft = m['score']['fullTime']['away'] or 0
                if is_home:
                    gf, ga = home_ft, away_ft
                else:
                    gf, ga = away_ft, home_ft
                outcomes.append('W' if gf > ga else ('D' if gf == ga else 'L'))
                gf_total += gf
                ga_total += ga
            form_str = ''.join(outcomes)
            count = len(outcomes)
            logger.info("Flashscore form %s: %s (GF:%g GA:%g)",
                        team_name, form_str, round(gf_total/count,2), round(ga_total/count,2))
            return {
                "team_id": team_id,
                "form": form_str,
                "last_5": outcomes,
                "goals_scored_avg": round(gf_total / count, 2),
                "goals_conceded_avg": round(ga_total / count, 2),
                "matches_analyzed": count,
            }
        except Exception as e:
            logger.warning("Flashscore exception for %s: %s", team_name, e)
            return None

    def get_h2h(self, home_team: str, away_team: str) -> dict:
        home_id = self._get_team_id(home_team)
        away_id = self._get_team_id(away_team)
        if not (home_id and away_id):
            return {"matches": [], "home_wins": 0, "draws": 0, "away_wins": 0}
        try:
            r = self.session.get(
                f"{BASE_URL}/teams/{home_id}/matches",
                params={"status": "FINISHED", "limit": 50},
                headers=HEADERS, timeout=15
            )
            if r.status_code != 200:
                return {"matches": [], "home_wins": 0, "draws": 0, "away_wins": 0}
            data = r.json()
            matches = data.get('matches', [])
            h2h = []
            for m in matches:
                opp_id = m['awayTeam']['id'] if m['homeTeam']['id'] == home_id else m['homeTeam']['id']
                if opp_id == away_id:
                    home_ft = m['score']['fullTime']['home'] or 0
                    away_ft = m['score']['fullTime']['away'] or 0
                    h2h.append({
                        "date": m['utcDate'][:10],
                        "home": m['homeTeam']['name'],
                        "away": m['awayTeam']['name'],
                        "score": f"{home_ft}-{away_ft}",
                    })
            home_wins = draws = away_wins = 0
            for m in h2h:
                hs, as_ = map(int, m['score'].split('-'))
                if m['home'].lower() == home_team.lower():
                    home_wins += (1 if hs > as_ else 0)
                    draws += (1 if hs == as_ else 0)
                    away_wins += (1 if hs < as_ else 0)
                else:
                    home_wins += (1 if hs < as_ else 0)
                    draws += (1 if hs == as_ else 0)
                    away_wins += (1 if hs > as_ else 0)
            return {
                "matches": h2h[:5],
                "home_wins": home_wins,
                "draws": draws,
                "away_wins": away_wins,
            }
        except Exception as e:
            logger.warning("Flashscore H2H error %s vs %s: %s", home_team, away_team, e)
            return {"matches": [], "home_wins": 0, "draws": 0, "away_wins": 0}

_scraper = FlashscoreCollector()
get_team_form = _scraper.get_team_form
get_h2h = _scraper.get_h2h
