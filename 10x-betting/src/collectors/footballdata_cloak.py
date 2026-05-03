"""
FootballDataCollector — free API fallback for Sofascore/Flashscore scrapers.
Uses Football-Data.org (requires FOOTBALL_DATA_API_KEY). Rate-limited; cached team map.
"""
import json, os, time, re, logging, requests
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class FootballDataCollector:
    BASE = "https://api.football-data.org/v4"
    CACHE_DIR = Path.home() / ".cache" / "10x-betting"
    CACHE_FILE = CACHE_DIR / "fd_team_map.json"
    RATE_LIMIT_SECONDS = 10  # conservative throttle
    
    def __init__(self):
        self.api_key = os.getenv("FOOTBALL_DATA_API_KEY")
        if not self.api_key:
            raise ValueError("FOOTBALL_DATA_API_KEY missing in environment")
        self._last_call = 0
        self._TEAM_MAP: Optional[Dict[str, int]] = None
        self._ensure_team_map()
        logger.info("FootballDataCollector ready (rate-limit: 10s)")

    # ── team mapping ────────────────────────────────────────────────────────────
    def _ensure_team_map(self):
        if self.CACHE_FILE.exists():
            try:
                data = json.loads(self.CACHE_FILE.read_text())
                if data.get("ts", 0) > time.time() - 86400:  # 24h TTL
                    self._TEAM_MAP = data["map"]
                    return
            except Exception:
                pass
        self._TEAM_MAP = self._build_team_map()
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.CACHE_FILE.write_text(json.dumps({"ts": time.time(), "map": self._TEAM_MAP}))

    def _build_team_map(self) -> Dict[str, int]:
        comps = ["PL", "PD", "CL", "SA", "LL1"]  # major European leagues
        team_map: Dict[str, int] = {}
        headers = {"X-Auth-Token": self.api_key}
        for code in comps:
            try:
                r = self._throttled_get(f"{self.BASE}/competitions/{code}/teams", headers=headers)
                if r.status_code != 200:
                    continue
                data = r.json()
                for team in data.get("teams", []):
                    tid = team.get("id")
                    name = team.get("name", "").strip()
                    short = team.get("shortName", "").strip()
                    for key in (name.lower(), short.lower()):
                        cleaned = re.sub(r'[^a-z0-9]', '', key)
                        if cleaned:
                            team_map[cleaned] = tid
            except Exception as e:
                logger.warning(f"Failed to index {code}: {e}")
        logger.info(f"Team map built: {len(team_map)} unique entries")
        return team_map

    def _get_team_id(self, team_name: str) -> Optional[int]:
        if self._TEAM_MAP is None:
            self._ensure_team_map()
        cleaned = re.sub(r'[^a-z0-9]', '', team_name.lower())
        direct = self._TEAM_MAP.get(cleaned)
        if direct:
            return direct
        # fuzzy fallback — match by similarity (e.g. 'manchestercity' vs 'manchestercityfc')
        from difflib import get_close_matches
        match = get_close_matches(cleaned, self._TEAM_MAP.keys(), n=1, cutoff=0.6)
        if match:
            return self._TEAM_MAP[match[0]]
        return None

    # ── HTTP with throttle ──────────────────────────────────────────────────────
    def _throttled_get(self, url: str, headers: Optional[Dict] = None) -> requests.Response:
        since = time.time() - self._last_call
        if since < self.RATE_LIMIT_SECONDS:
            time.sleep(self.RATE_LIMIT_SECONDS - since)
        r = requests.get(url, headers=headers or {}, timeout=15)
        self._last_call = time.time()
        if r.status_code == 429:
            logger.warning("API 429 — sleeping 60s")
            time.sleep(60)
            r = requests.get(url, headers=headers or {}, timeout=15)
            self._last_call = time.time()
        return r

    # ── public API ────────────────────────────────────────────────────────────
    def get_team_form(self, team_name: str) -> Optional[Dict[str, Any]]:
        tid = self._get_team_id(team_name)
        if not tid:
            logger.warning(f"Team ID not found: {team_name}")
            return None
        headers = {"X-Auth-Token": self.api_key}
        url = f"{self.BASE}/teams/{tid}/matches?status=FINISHED&limit=25"
        r = self._throttled_get(url, headers=headers)
        if r.status_code != 200:
            logger.error(f"API error {r.status_code} for {team_name}")
            return None
        matches = r.json().get("matches", [])[:5]
        if not matches:
            return None
        form_chars = []
        gf = ga = 0
        last_5 = []
        for m in matches:
            home_id = m.get("homeTeam", {}).get("id")
            away_id = m.get("awayTeam", {}).get("id")
            score = m.get("score", {}).get("fullTime", {})
            hg = score.get("home", 0) or 0
            ag = score.get("away", 0) or 0
            if home_id == tid:
                result = "W" if hg > ag else ("D" if hg == ag else "L")
                gf += hg; ga += ag
                opp = m.get("awayTeam", {}).get("name", "")
                venue = "H"
            else:
                result = "W" if ag > hg else ("D" if ag == hg else "L")
                gf += ag; ga += hg
                opp = m.get("homeTeam", {}).get("name", "")
                venue = "A"
            form_chars.append(result)
            last_5.append({"opponent": opp, "home_away": venue, "score": f"{hg}-{ag}", "result": result})
        return {
            "form": "".join(form_chars),
            "last_5": last_5,
            "goals_scored_avg": round(gf / len(matches), 2),
            "goals_conceded_avg": round(ga / len(matches), 2),
            "matches_analyzed": len(matches),
            "team_id": tid,
        }

    def get_h2h(self, home_team: str, away_team: str) -> Optional[Dict[str, Any]]:
        home_id = self._get_team_id(home_team)
        away_id = self._get_team_id(away_team)
        if not home_id or not away_id:
            logger.warning(f"H2H — unknown team: {home_team}={home_id}, {away_team}={away_id}")
            return None
        headers = {"X-Auth-Token": self.api_key}
        url = f"{self.BASE}/teams/{home_id}/matches?status=FINISHED&limit=50"
        r = self._throttled_get(url, headers=headers)
        if r.status_code != 200:
            return None
        h2h_raw = []
        for m in r.json().get("matches", []):
            opp_id = m.get("awayTeam", {}).get("id") if m.get("homeTeam", {}).get("id") == home_id else m.get("homeTeam", {}).get("id")
            if opp_id != away_id:
                continue
            hg = m.get("score", {}).get("fullTime", {}).get("home", 0) or 0
            ag = m.get("score", {}).get("fullTime", {}).get("away", 0) or 0
            if m["homeTeam"]["id"] == home_id:
                res = "W" if hg > ag else ("D" if hg == ag else "L")
            else:
                res = "W" if ag > hg else ("D" if ag == hg else "L")
            h2h_raw.append(res)
        h2h = h2h_raw[:5]
        if not h2h:
            return {"matches": 0}
        n = len(h2h)
        wins = sum(1 for r in h2h if r == "W")
        draws = sum(1 for r in h2h if r == "D")
        losses = sum(1 for r in h2h if r == "L")
        return {
            "matches": n,
            "home_wins_pct": round(wins/n,2) if m["homeTeam"]["id"] == home_id else None,
            "draw_pct": round(draws/n,2),
            "away_wins_pct": round(losses/n,2) if m["homeTeam"]["id"] != home_id else None,
            "recent_results": h2h,
        }
