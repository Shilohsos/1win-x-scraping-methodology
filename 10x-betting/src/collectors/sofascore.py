import logging
import requests
import time
import re
from typing import Optional

logger = logging.getLogger("10xbet.sofascore")

CAMOFOX_BASE = "http://localhost:9377"

TEAM_IDS = {
    "Arsenal": 42, "Chelsea": 38, "Manchester City": 17, "Manchester United": 35,
    "Liverpool": 44, "Tottenham": 33, "Newcastle": 39, "Aston Villa": 40,
    "West Ham": 37, "Brighton": 211, "Brentford": 7537, "Fulham": 43,
    "Crystal Palace": 7, "Wolves": 3, "Everton": 48, "Nottm Forest": 14,
    "Leicester": 31, "Ipswich": 32, "Southampton": 45, "Leeds United": 46,
    "Real Madrid": 2829, "Barcelona": 2817, "Atletico Madrid": 2836,
    "Sevilla": 2833, "Valencia": 2828, "Athletic Bilbao": 2818,
    "Real Sociedad": 2824, "Villarreal": 2826, "Betis": 2819,
    "Osasuna": 2823, "Celta Vigo": 2821, "Espanyol": 2820,
    "Alaves": 2816, "Getafe": 2859, "Rayo Vallecano": 2862,

    "Girona FC": 2209,
    "RCD Mallorca": 2207,
    "Levante UD": 2230,
    "Athletic Club": 2818,
    "Club Atlético de Madrid": 2836,
    "Deportivo Alavés": 2816,
}

class SofascoreCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}
        logger.info("SofascoreCollector ready (camofox browser, proxy bypassed)")

    def _create_tab(self, user_id: str = "sofascore_bot") -> str:
        r = self.session.post(f"{CAMOFOX_BASE}/tabs",
            json={"userId": user_id, "sessionKey": "sofascore"}, timeout=10)
        r.raise_for_status()
        return r.json()["tabId"]

    def _close_tab(self, tab_id: str, user_id: str = "sofascore_bot"):
        try:
            self.session.delete(f"{CAMOFOX_BASE}/tabs/{tab_id}",
                params={"userId": user_id}, timeout=5)
        except Exception:
            pass

    def _navigate(self, tab_id: str, url: str, user_id: str = "sofascore_bot"):
        r = self.session.post(f"{CAMOFOX_BASE}/tabs/{tab_id}/navigate",
            json={"userId": user_id, "url": url}, timeout=30)
        r.raise_for_status()
        time.sleep(4)

    def _scroll_burst(self, tab_id: str, user_id: str = "sofascore_bot"):
        for i in range(20):
            try:
                self.session.post(f"{CAMOFOX_BASE}/tabs/{tab_id}/scroll",
                    json={"userId": user_id, "direction": "down", "amount": 1200},
                    timeout=8)
                time.sleep(0.7)
            except Exception:
                break

    def _get_snapshot_text(self, tab_id: str, user_id: str = "sofascore_bot") -> str:
        r = self.session.get(f"{CAMOFOX_BASE}/tabs/{tab_id}/snapshot",
            params={"userId": user_id}, timeout=10)
        r.raise_for_status()
        return r.text

    def _parse_matches(self, text: str) -> list:
        score_pat = re.compile(r'([A-Za-z]+)?\s*(\d+)\s*[-–]\s*(\d+)\s*([A-Za-z]+)?')
        matches = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            m = score_pat.search(line)
            if m:
                home, gf, ga, away = m.groups()
                try:
                    gf_i, ga_i = int(gf), int(ga)
                except ValueError:
                    continue
                if gf_i > 20 or ga_i > 20:
                    continue
                wk = "W" if gf_i > ga_i else "D" if gf_i == ga_i else "L"
                matches.append({"gf": gf_i, "ga": ga_i, "outcome": wk})
        return matches

    def get_team_form(self, team_name: str) -> Optional[dict]:
        team_id = TEAM_IDS.get(team_name)
        if not team_id:
            for k, v in TEAM_IDS.items():
                if k.lower() in team_name.lower():
                    team_id = v
                    break
        if not team_id:
            logger.warning("Sofascore: unknown team %s", team_name)
            return None

        url = f"https://www.sofascore.com/team/football/{team_name.lower().replace(' ', '-')}/{team_id}"
        tab = None
        try:
            tab = self._create_tab()
            self._navigate(tab, url)
            self._scroll_burst(tab)
            snapshot = self._get_snapshot_text(tab)
            matches = self._parse_matches(snapshot)
            if len(matches) < 3:
                # Try evaluate-based extraction of score lines
                try:
                    js = 'document.body.innerText.split("\n").filter(l => /\d+\s*[-–]\s*\d+/.test(l)).slice(-20)'
                    r = self.session.post(f"{CAMOFOX_BASE}/tabs/{tab_id}/evaluate",
                        json={"userId":"sofascore_bot","expression":js}, timeout=15)
                    if r.ok:
                        lines = r.json().get("result", [])
                        # Re-parse
                        matches = self._parse_matches("\n".join(lines))
                except Exception:
                    pass
            last5 = matches[-5:] if matches else []
            if not last5:
                return {"team_id": team_id, "form": "", "last_5": [],
                        "goals_scored_avg": 0.0, "goals_conceded_avg": 0.0,
                        "matches_analyzed": 0}
            form_str = "".join(m["outcome"] for m in last5)
            count = len(last5)
            gf_sum = sum(m["gf"] for m in last5)
            ga_sum = sum(m["ga"] for m in last5)
            return {
                "team_id": team_id,
                "form": form_str,
                "last_5": [m["outcome"] for m in last5],
                "goals_scored_avg": round(gf_sum / count, 2),
                "goals_conceded_avg": round(ga_sum / count, 2),
                "matches_analyzed": count,
            }
        except Exception as e:
            logger.warning("Sofascore browser error for %s: %s", team_name, e)
            return None
        finally:
            if tab:
                self._close_tab(tab)

_scraper = SofascoreCollector()
get_team_form = _scraper.get_team_form
