import logging
import os
import requests
import time
import re
import json
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger("10xbet.flashscore")

# ── Football-Data.org configuration
API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")  # read at module load (after dotenv)
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY} if API_KEY else {}

COMP_CODES = ["PL", "CL", "PD"]   # Premier League | Champions League | La Liga

# ── Rate-limit handling (FD.org ≈ 8 req/60s burst)
_LAST_API_CALL = 0

# ── Team ID cache
_CACHE_PATH = Path("/root/10x-betting/.cache/fd_team_map.json")
_TEAM_MAP: Dict[str, int] = {}
_LAST_REFRESH = 0

def _clean_name(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())

def _throttle():
    """Ensure at least 10s between any FD.org request (safe margin)."""
    global _LAST_API_CALL
    now = time.time()
    delta = now - _LAST_API_CALL
    if delta < 10.0:
        sleep = 10.0 - delta
        time.sleep(sleep)
    _LAST_API_CALL = time.time()

def _refresh_team_map() -> bool:
    """Load or download PL/CL/PD team ID mapping. Returns True on success."""
    global _TEAM_MAP, _LAST_REFRESH
    # Try persistent cache first
    if _CACHE_PATH.exists():
        try:
            with open(_CACHE_PATH) as fh:
                _TEAM_MAP.update(json.load(fh))
            _LAST_REFRESH = _CACHE_PATH.stat().st_mtime
            logger.info("Flashscore: team map loaded from cache (%d teams)", len(_TEAM_MAP))
            return True
        except json.JSONDecodeError as e:
            logger.warning("Team-map cache corrupted: %s — fetching fresh", e)
    
    _TEAM_MAP.clear()
    COMP_CODES: ["PL", "CL", "PD"]
    for code in ["PL", "CL", "PD"]:
        _throttle()
        try:
            r = requests.get(f"{BASE_URL}/competitions/{code}/teams",
                             headers=HEADERS, timeout=15)
            if r.status_code == 200:
                teams = r.json().get('teams', [])
                for t in teams:
                    tid = t['id']
                    name = t['name']
                    _TEAM_MAP[name.lower()] = tid
                    _TEAM_MAP[_clean_name(name)] = tid
                    short = t.get('shortName')
                    if short:
                        _TEAM_MAP[short.lower()] = tid
            else:
                logger.warning("FD.org %s teams: HTTP %s", code, r.status_code)
        except Exception as e:
            logger.warning("FD.org %s teams fetch failed: %s", code, e)

    # Additional human-readable aliases (names differ from FD.org canonical)

    # Persist to cache
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(_CACHE_PATH, 'w') as fh:
            json.dump(_TEAM_MAP, fh)
    except Exception:
        pass
    _LAST_REFRESH = time.time()
    logger.info("Flashscore: team map refreshed — %d teams", len(_TEAM_MAP))
    return True

# Initialise at module import (called once)
if not _TEAM_MAP and API_KEY:
    _refresh_team_map()

class FlashscoreCollector:
    """Production Flashscore stand-in that reads team form from Football-Data.org."""

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}
        self._team_form_cache: Dict[str, Dict] = {}
        self._h2h_cache: Dict[str, Dict] = {}

    # Internal helpers
    def _get_team_id(self, team_name: str) -> Optional[int]:
        norm = team_name.strip().lower()
        if norm in _TEAM_MAP:
            return _TEAM_MAP[norm]
        clean = _clean_name(norm)
        if clean in _TEAM_MAP:
            return _TEAM_MAP[clean]
        logger.warning("Flashscore: unknown team '%s'", team_name)
        return None

    # Public interfaces
    def get_team_form(self, team_name: str) -> Optional[dict]:
        """Return last-5 match form for a team from Football-Data.org."""
        team_id = self._get_team_id(team_name)
        if not team_id:
            return None
        return self._fetch_team_form(team_id, team_name)

    def _fetch_team_form(self, team_id: int, team_name: str = "", lookback: int = 0) -> Optional[dict]:
        """Core form fetcher with cache, rate-limit throttle, and multi-pass fallback."""
        cache_key = f"fd:{team_id}"
        if cache_key in self._team_form_cache:
            return self._team_form_cache[cache_key]

        # Try small fetch first; fallback to larger window if insufficient
        attempts = [5] if lookback else [5, 20, 50]
        for limit in attempts:
            _throttle()
            try:
                r = requests.get(
                    f"{BASE_URL}/teams/{team_id}/matches",
                    params={"status": "FINISHED", "limit": limit},
                    headers=HEADERS,
                    timeout=15,
                )
                if r.status_code != 200:
                    logger.warning("FD.org form team %d: HTTP %s", team_id, r.status_code)
                    return None
                matches = [m for m in r.json().get('matches', [])
                           if m.get('score', {}).get('fullTime', {}).get('home') is not None]
                matches.sort(key=lambda m: m.get('utcDate', ''), reverse=True)
            except Exception as e:
                logger.warning("FD.org form error team %d: %s", team_id, e)
                return None
            if len(matches) >= 5:
                break
            # Not enough results — try next larger window

        last5 = matches[:5] if matches else []
        results = []
        gf = gc = 0
        for m in last5:
            home_id  = m.get('homeTeam', {}).get('id')
            home_gl  = m['score']['fullTime']['home']
            away_gl  = m['score']['fullTime']['away']
            is_home = (home_id == team_id)
            scored  = home_gl if is_home else away_gl
            conceded = away_gl if is_home else home_gl
            if is_home:
                result = 'W' if home_gl > away_gl else 'L' if home_gl < away_gl else 'D'
            else:
                result = 'W' if away_gl > home_gl else 'L' if away_gl < home_gl else 'D'
            results.append(result)
            gf += scored
            gc += conceded

        n = len(results)
        form = {
            'form':                        ''.join(results),
            'last_5':                      results,
            'matches_analyzed':            n,
            'team_id':                     team_id,
            'goals_scored_avg':            round(gf / n, 2) if n else 0.0,
            'goals_conceded_avg':          round(gc / n, 2) if n else 0.0,
            # Legacy keys kept for compatibility
            'avg_goals':                   round((gf + gc) / n / 2, 2) if n else 0.0,
            'win_pct':                     round(results.count('W') / n * 100, 1) if n else 0.0,
        }
        self._team_form_cache[cache_key] = form
        logger.info(
            "Flashscore form %s: %s (GF %.2f / GA %.2f)",
            team_name or str(team_id), form['form'], form['goals_scored_avg'], form['goals_conceded_avg']
        )
        return form

    def get_h2h(self, home_team: str, away_team: str) -> dict:
        """Head-to-head record from Football-Data.org (home-team perspective)."""
        home_id = self._get_team_id(home_team)
        away_id = self._get_team_id(away_team)
        if not home_id or not away_id:
            return {'last_5': [], 'avg_goals': 0, 'home_win_pct': 0,
                    'draw_pct': 0, 'away_win_pct': 0,
                    'home_goals_avg': 0, 'away_goals_avg': 0,
                    'matches_analyzed': 0}

        key = f"h2h:{home_id}:{away_id}"
        if key in self._h2h_cache:
            return self._h2h_cache[key]

        _throttle()
        try:
            r = requests.get(
                f"{BASE_URL}/teams/{home_id}/matches",
                params={"status": "FINISHED", "limit": 50},
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                return _empty_h2h()
            matches = [m for m in r.json().get('matches', [])
                       if m.get('score', {}).get('fullTime', {}).get('home') is not None
                       and (m.get('homeTeam', {}).get('id') == away_id
                            or m.get('awayTeam', {}).get('id') == away_id)]
            matches.sort(key=lambda m: m.get('utcDate', ''), reverse=True)
            last5 = matches[:5]
        except Exception as e:
            logger.warning("H2H fetch error (%s vs %s): %s", home_team, away_team, e)
            return _empty_h2h()

        wins = draws = total = 0
        hg = ag = 0
        for m in last5:
            home_gl  = m['score']['fullTime']['home']
            away_gl  = m['score']['fullTime']['away']
            hs_id    = m.get('homeTeam', {}).get('id')
            if hs_id == home_id:
                # home-team perspective (this match is at home vs away_id)
                if home_gl > away_gl: wins += 1
                elif home_gl == away_gl: draws += 1
                hg += home_gl; ag += away_gl
            else:
                # this fixture was away for us; reverse
                if away_gl > home_gl: wins += 1
                elif away_gl == home_gl: draws += 1
                hg += away_gl; ag += home_gl
            total += 1

        h2h = {
            'last_5':          [],
            'avg_goals':       round((hg + ag) / total, 2) if total else 0.0,
            'home_win_pct':    round(wins / total * 100, 1) if total else 0.0,
            'draw_pct':        round(draws / total * 100, 1) if total else 0.0,
            'away_win_pct':    round((total - wins - draws) / total * 100, 1) if total else 0.0,
            'home_goals_avg':  round(hg / total, 2) if total else 0.0,
            'away_goals_avg':  round(ag / total, 2) if total else 0.0,
            'matches_analyzed': total,
        }
        self._h2h_cache[key] = h2h
        logger.info(
            "Flashscore H2H %s vs %s: %.1f%%/%.1f%%/%.1f%% (n=%d)",
            home_team, away_team,
            h2h['home_win_pct'], h2h['draw_pct'], h2h['away_win_pct'],
            total,
        )
        return h2h

def _empty_h2h() -> dict:
    return {'last_5': [], 'avg_goals': 0, 'home_win_pct': 0,
            'draw_pct': 0, 'away_win_pct': 0,
            'home_goals_avg': 0, 'away_goals_avg': 0,
            'matches_analyzed': 0}
