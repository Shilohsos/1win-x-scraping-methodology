import requests
import logging

logger = logging.getLogger("10xbet.flashscore")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12) "
        "AppleWebKit/537.36 Chrome/112.0.0.0 Mobile Safari/537.36"
    ),
    "x-fsign": "SW9D1eZo",
}

class FlashscoreCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        logger.info("FlashscoreCollector ready")

    def get_h2h(self, home_team, away_team):
        try:
            url = "https://d.flashscore.com/x/feed/proxy-search"
            r = self.session.get(
                url,
                params={"q": f"{home_team} {away_team}", "l": 1, "s": 4},
                timeout=10,
            )
            results = []
            if r.status_code == 200:
                lines = [l for l in r.text.split("\n") if "~" in l]
                for line in lines[:5]:
                    parts = line.split("~")
                    if len(parts) >= 5:
                        results.append({
                            "home": parts[2] if len(parts) > 2 else "",
                            "away": parts[3] if len(parts) > 3 else "",
                            "score": parts[4] if len(parts) > 4 else "",
                        })
            home_wins = sum(
                1 for r in results
                if home_team.lower() in r.get("home", "").lower()
            )
            away_wins = sum(
                1 for r in results
                if away_team.lower() in r.get("away", "").lower()
            )
            draws = max(0, len(results) - home_wins - away_wins)
            logger.info(
                "H2H %s vs %s: %d-%d-%d",
                home_team, away_team, home_wins, draws, away_wins
            )
            return {
                "matches": results,
                "home_wins": home_wins,
                "away_wins": away_wins,
                "draws": draws,
            }
        except Exception as e:
            logger.warning("Flashscore H2H error: %s", e)
            return {"matches": [], "home_wins": 0, "away_wins": 0, "draws": 0}
