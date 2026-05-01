import requests
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger("10xbet.official")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; Infinix X6816D) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/112.0.0.0 Mobile Safari/537.36"
    )
}

LEAGUE_SOURCES = {
    "PL": "https://www.premierleague.com/injuries",
    "PD": "https://www.laliga.com/en-GB/laliga-ea-sports/injuries",
    "CL": "https://www.uefa.com/uefachampionsleague/news/suspensions/",
}

EPL_CLUBS = {
    "Arsenal":           "https://www.arsenal.com/news/team-news",
    "Chelsea":           "https://www.chelseafc.com/en/news/latest/team-news",
    "Manchester City":   "https://www.mancity.com/news/mens/team-news",
    "Manchester United": "https://www.manutd.com/en/News/First-Team-News",
    "Liverpool":         "https://www.liverpoolfc.com/news/first-team",
    "Tottenham":         "https://www.tottenhamhotspur.com/news/first-team/",
    "Newcastle":         "https://www.nufc.co.uk/news/latest-news/",
    "Aston Villa":       "https://www.avfc.co.uk/news/first-team-news/",
    "West Ham":          "https://www.whufc.com/news/articles",
    "Brighton":          "https://www.brightonandhovealbion.com/news/first-team",
    "Brentford":         "https://www.brentfordfc.com/en/news/first-team",
    "Fulham":            "https://www.fulhamfc.com/news/",
    "Crystal Palace":    "https://www.cpfc.co.uk/news/first-team/",
    "Wolves":            "https://www.wolves.co.uk/news/first-team/",
    "Everton":           "https://www.evertonfc.com/news",
    "Nottm Forest":      "https://www.nottinghamforest.co.uk/news/",
    "Leicester":         "https://www.lcfc.com/news/first-team",
    "Ipswich":           "https://www.itfc.co.uk/news/",
    "Southampton":       "https://www.southamptonfc.com/en/news",
    "Leeds United":      "https://www.leedsunited.com/en/news",
}

LALIGA_CLUBS = {
    "Real Madrid":            "https://www.realmadrid.com/en/news/football",
    "Barcelona":              "https://www.fcbarcelona.com/en/news",
    "Atletico Madrid":        "https://en.atleticodemadrid.com/noticias",
    "Sevilla":                "https://www.sevillafc.es/en/news",
    "Valencia":               "https://www.valenciacf.com/en/news",
    "Athletic Bilbao":        "https://www.athletic-club.eus/en/news",
    "Real Sociedad":          "https://www.realsociedad.eus/en/news",
    "Villarreal":             "https://www.villarrealcf.es/en/noticias/",
    "Betis":                  "https://www.realbetisbalompie.es/en/news",
    "Osasuna":                "https://www.osasuna.es/noticias",
}

ALL_CLUBS = {**EPL_CLUBS, **LALIGA_CLUBS}

class OfficialSitesCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}
        self.session.headers.update(HEADERS)
        logger.info("OfficialSitesCollector ready — %d clubs", len(ALL_CLUBS))

    def get_team_news(self, team_name):
        url = ALL_CLUBS.get(team_name)
        if not url:
            for k, v in ALL_CLUBS.items():
                if (k.lower() in team_name.lower()
                           or team_name.lower() in k.lower()):
                    url = v
                    break
        if not url:
            logger.debug("No official site mapped for %s", team_name)
            return []
        try:
            r = self.session.get(url, timeout=12)
            soup = BeautifulSoup(r.text, "lxml")
            headlines = []
            for tag in soup.find_all(["h2", "h3", "h4"], limit=10):
                text = tag.get_text(strip=True)
                if len(text) > 15:
                    headlines.append(text)
            logger.info(
                "Official site %s: %d headlines", team_name, len(headlines)
            )
            return headlines
        except Exception as e:
            logger.warning("Official site error %s: %s", team_name, e)
            return []
