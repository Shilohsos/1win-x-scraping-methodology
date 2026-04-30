import requests
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger("10xbet.oddschecker")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

class OddscheckerCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        logger.info("OddscheckerCollector ready")

    def get_market_sentiment(self, home_team, away_team):
        try:
            home_slug = home_team.lower().replace(" ", "-")
            away_slug = away_team.lower().replace(" ", "-")
            url = (
                f"https://www.oddschecker.com/football/english/"
                f"premier-league/{home_slug}-{away_slug}/winner"
            )
            r = self.session.get(url, timeout=12)
            soup = BeautifulSoup(r.text, "lxml")
            sentiment = {
                "home_favoured": False,
                "away_favoured": False,
                "public_lean": "neutral",
            }
            odds_cells = soup.select("td.bc")
            if odds_cells:
                try:
                    home_odds = float(odds_cells[0].get_text(strip=True))
                    away_odds = float(odds_cells[-1].get_text(strip=True))
                    if home_odds < away_odds:
                        sentiment["home_favoured"] = True
                        sentiment["public_lean"] = "home"
                    else:
                        sentiment["away_favoured"] = True
                        sentiment["public_lean"] = "away"
                except (ValueError, IndexError):
                    pass
            logger.info(
                "Oddschecker: %s vs %s lean=%s",
                home_team, away_team, sentiment["public_lean"]
            )
            return sentiment
        except Exception as e:
            logger.warning("Oddschecker error: %s", e)
            return {"public_lean": "unknown"}
