import requests
import logging

logger = logging.getLogger("10xbet.sofascore")

BASE = "https://api.sofascore.com/api/v1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; Infinix X6816D) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/112.0.0.0 Mobile Safari/537.36"
    ),
    "Referer": "https://www.sofascore.com/",
    "Accept": "application/json",
}

class SofascoreCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        logger.info("SofascoreCollector ready")

    def get_team_form(self, team_name):
        try:
            r = self.session.get(
                f"{BASE}/search/all",
                params={"q": team_name},
                timeout=10,
            )
            data = r.json()
            teams = data.get("teams", {}).get("hits", [])
            if not teams:
                return None
            team_id = teams[0]["entity"]["id"]
            r2 = self.session.get(
                f"{BASE}/team/{team_id}/events/last/0",
                timeout=10,
            )
            events = r2.json().get("events", [])
            form = []
            goals_scored = []
            goals_conceded = []
            for e in events[-5:]:
                ht = e.get("homeTeam", {}).get("name", "")
                at = e.get("awayTeam", {}).get("name", "")
                hs = e.get("homeScore", {}).get("current", 0)
                as_ = e.get("awayScore", {}).get("current", 0)
                is_home = ht.lower() == team_name.lower()
                if is_home:
                    result = "W" if hs > as_ else ("D" if hs == as_ else "L")
                    goals_scored.append(hs)
                    goals_conceded.append(as_)
                else:
                    result = "W" if as_ > hs else ("D" if as_ == hs else "L")
                    goals_scored.append(as_)
                    goals_conceded.append(hs)
                form.append(result)
            return {
                "team_id": team_id,
                "form": "".join(form),
                "last_5": form,
                "goals_scored_avg": round(
                    sum(goals_scored) / len(goals_scored), 2
                ) if goals_scored else 0,
                "goals_conceded_avg": round(
                    sum(goals_conceded) / len(goals_conceded), 2
                ) if goals_conceded else 0,
            }
        except Exception as e:
            logger.warning("Sofascore team form error %s: %s", team_name, e)
            return None

    def get_referee_stats(self, referee_name):
        try:
            r = self.session.get(
                f"{BASE}/search/all",
                params={"q": referee_name},
                timeout=10,
            )
            data = r.json()
            refs = data.get("referees", {}).get("hits", [])
            if not refs:
                return None
            ref_id = refs[0]["entity"]["id"]
            r2 = self.session.get(
                f"{BASE}/referee/{ref_id}/events/last/0",
                timeout=10,
            )
            events = r2.json().get("events", [])
            yellows = []
            reds = []
            for e in events[-20:]:
                stats = e.get("statistics", {})
                yellows.append(stats.get("yellowCards", 0))
                reds.append(stats.get("redCards", 0))
            avg_y = sum(yellows) / len(yellows) if yellows else 0
            avg_r = sum(reds) / len(reds) if reds else 0
            return {
                "referee": referee_name,
                "avg_yellow": round(avg_y, 2),
                "avg_red": round(avg_r, 2),
                "strictness": round((avg_y * 1 + avg_r * 3), 2),
                "matches": len(events),
            }
        except Exception as e:
            logger.warning("Sofascore referee error %s: %s", referee_name, e)
            return None

    def get_player_form(self, player_name, team_name=""):
        try:
            r = self.session.get(
                f"{BASE}/search/all",
                params={"q": player_name},
                timeout=10,
            )
            players = r.json().get("players", {}).get("hits", [])
            if not players:
                return None
            pid = players[0]["entity"]["id"]
            r2 = self.session.get(
                f"{BASE}/player/{pid}/events/last/0",
                timeout=10,
            )
            events = r2.json().get("events", [])
            ratings = []
            for e in events[-5:]:
                home_stats = e.get("playerStatistics", {}).get("home", [])
                away_stats = e.get("playerStatistics", {}).get("away", [])
                for player in home_stats + away_stats:
                    if player.get("player", {}).get("id") == pid:
                        rating = player.get("rating", 0)
                        if rating:
                            ratings.append(float(rating))
            avg_rating = sum(ratings) / len(ratings) if ratings else 0
            return {
                "player": player_name,
                "avg_rating": round(avg_rating, 2),
                "form": (
                    "good" if avg_rating >= 7.0
                    else "poor" if avg_rating < 6.0
                    else "average"
                ),
            }
        except Exception as e:
            logger.warning("Sofascore player error %s: %s", player_name, e)
            return None
