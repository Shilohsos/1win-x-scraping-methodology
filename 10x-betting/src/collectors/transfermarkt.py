import requests
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger("10xbet.transfermarkt")

BASE = "https://www.transfermarkt.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class TransfermarktCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        logger.info("TransfermarktCollector ready")

    def get_team_injuries(self, team_name):
        try:
            r = self.session.get(
                f"{BASE}/schnellsuche/ergebnis/schnellsuche",
                params={"query": team_name},
                timeout=12,
            )
            soup = BeautifulSoup(r.text, "lxml")
            team_link = soup.select_one("table.items td.hauptlink a")
            if not team_link:
                return []
            team_url = BASE + team_link["href"]
            injury_url = team_url.replace(
                "/startseite/", "/sperrenundverletzungen/"
            )
            r2 = self.session.get(injury_url, timeout=12)
            soup2 = BeautifulSoup(r2.text, "lxml")
            injuries = []
            rows = soup2.select("table.items tbody tr")
            for row in rows[:10]:
                cols = row.find_all("td")
                if len(cols) >= 4:
                    player = cols[1].get_text(strip=True)
                    injury = cols[3].get_text(strip=True)
                    return_date = (
                        cols[4].get_text(strip=True)
                        if len(cols) > 4 else "Unknown"
                    )
                    if player:
                        injuries.append({
                            "player": player,
                            "injury": injury,
                            "return": return_date,
                        })
            logger.info(
                "Transfermarkt: %d injuries for %s",
                len(injuries), team_name
            )
            return injuries
        except Exception as e:
            logger.warning(
                "Transfermarkt injury error %s: %s", team_name, e
            )
            return []

    def get_motivation_signals(self, player_name):
        signals = []
        try:
            r = self.session.get(
                f"{BASE}/schnellsuche/ergebnis/schnellsuche",
                params={"query": player_name},
                timeout=12,
            )
            soup = BeautifulSoup(r.text, "lxml")
            contract_info = soup.find(
                string=lambda t: t and "contract" in t.lower()
            )
            if contract_info:
                signals.append("contract_expiry_soon")
            transfer_link = soup.find(
                "a", string=lambda t: t and "transfer" in t.lower()
            )
            if transfer_link:
                signals.append("transfer_rumour")
        except Exception as e:
            logger.warning(
                "Transfermarkt motivation error %s: %s", player_name, e
            )
        return signals
