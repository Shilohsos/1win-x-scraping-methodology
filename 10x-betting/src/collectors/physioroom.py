import requests
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger("10xbet.physioroom")

BASE = "https://www.physioroom.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

TEAM_SLUGS = {
    "Arsenal":           "arsenal",
    "Chelsea":           "chelsea",
    "Manchester City":   "manchester-city",
    "Manchester United": "manchester-united",
    "Liverpool":         "liverpool",
    "Tottenham":         "tottenham-hotspur",
    "Newcastle":         "newcastle-united",
    "Aston Villa":       "aston-villa",
    "West Ham":          "west-ham-united",
    "Brighton":          "brighton-hove-albion",
    "Brentford":         "brentford",
    "Fulham":            "fulham",
    "Crystal Palace":    "crystal-palace",
    "Wolves":            "wolverhampton-wanderers",
    "Everton":           "everton",
    "Nottm Forest":      "nottingham-forest",
    "Leicester":         "leicester-city",
    "Ipswich":           "ipswich-town",
    "Southampton":       "southampton",
    "Leeds United":      "leeds-united",
}

class PhysioroomCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        logger.info("PhysioroomCollector ready")

    def get_injuries(self, team_name):
        slug = TEAM_SLUGS.get(team_name)
        if not slug:
            for k, v in TEAM_SLUGS.items():
                if k.lower() in team_name.lower():
                    slug = v
                    break
        if not slug:
            logger.debug("No Physioroom slug for %s", team_name)
            return []
        try:
            url = f"{BASE}/news/injuries/premiership/{slug}/"
            r = self.session.get(url, timeout=12)
            soup = BeautifulSoup(r.text, "lxml")
            injuries = []
            rows = soup.select("table tr")
            for row in rows[1:10]:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    player = cols[0].get_text(strip=True)
                    injury_type = cols[1].get_text(strip=True)
                    ret = cols[2].get_text(strip=True)
                    if player:
                        injuries.append({
                            "player": player,
                            "injury": injury_type,
                            "return": ret,
                        })
            logger.info(
                "Physioroom: %d injuries for %s", len(injuries), team_name
            )
            return injuries
        except Exception as e:
            logger.warning("Physioroom error %s: %s", team_name, e)
            return []
