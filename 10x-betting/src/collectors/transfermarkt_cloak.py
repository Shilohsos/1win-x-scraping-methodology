import logging
import sys
import time
import nest_asyncio
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger("10xbet.transfermarkt_cloak")

# Patch event loop for Playwright sync compatibility
try:
    nest_asyncio.apply()
except Exception:
    pass

# Add CloakBrowser venv to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cloakbrowser-venv" / "lib" / "python3.12" / "site-packages"))
from cloakbrowser import launch

BASE = "https://www.transfermarkt.com"

class TransfermarktCloakCollector:
    def __init__(self):
        self.browser = None
        logger.info("TransfermarktCloakCollector ready (CloakBrowser)")

    def _ensure_browser(self):
        if self.browser is None:
            self.browser = launch(headless=True, humanize=False)

    def get_team_injuries(self, team_name: str) -> List[Dict[str, str]]:
        """
        Navigate to Transfermarkt team injury/suspension page
        and extract injured players, injury type, and return dates.
        """
        try:
            self._ensure_browser()
            page = self.browser.new_page()

            # Step 1: Search for team — select FIRST TEAM link (verein), not person
            search_url = f"{BASE}/schnellsuche/ergebnis/schnellsuche"
            page.goto(f"{search_url}?query={team_name}", timeout=30000)
            time.sleep(2)

            team_link = page.evaluate("""(teamName) => {
                // Find all team result links (href contains "/verein/")
                const links = document.querySelectorAll('table.items td.hauptlink a[href*="/verein/"]');
                if (links.length > 0) return links[0].href;
                // Fallback: first link with /startseite/
                const first = document.querySelector('table.items td.hauptlink a[href*="/startseite/"]');
                return first ? first.href : null;
            }""", team_name)

            if not team_link:
                logger.warning("Transfermarkt: team not found for %s", team_name)
                return []

            # Step 2: Navigate to injuries page
            injury_url = team_link.replace("/startseite/", "/sperrenundverletzungen/")
            logger.debug("Fetching injuries from %s", injury_url)
            page.goto(injury_url, timeout=30000)
            time.sleep(2)

            # Scroll to load table
            page.keyboard.press("End")
            time.sleep(1)

            # Extract injury rows — Transfermarkt uses a complex table:
            # Rows with 9 cols carry data: [0]=player+pos, [1]="", [2]=name, [3]=pos, [4]=age, [5]=injury, [6]=since, [7]=return, [8]=missed
            # Skip 1–2 col decorative rows; take only 9-col rows.
            rows = page.evaluate("""() => {
              const table = document.querySelector('table.items tbody');
              if (!table) return [];
              return Array.from(table.querySelectorAll('tr')).slice(0, 30).map(tr => {
                const tds = Array.from(tr.querySelectorAll('td'));
                return {
                  colCount: tds.length,
                  player: tds.length === 9 ? tds[2].innerText.trim() : '',
                  injury: tds.length === 9 ? tds[5].innerText.trim() : '',
                  return_date: tds.length === 9 ? tds[7].innerText.trim() : '',
                  since_date: tds.length === 9 ? tds[6].innerText.trim() : '',
                  age: tds.length === 9 ? tds[4].innerText.trim() : '',
                  missed: tds.length === 9 ? tds[8].innerText.trim() : ''
                };
              }).filter(row => row.player);
            }""")

            injuries = []
            for row in rows:
                if row.get("player"):
                    injuries.append({
                        "player": row["player"],
                        "injury": row["injury"],
                        "return_date": row["return_date"],
                        "since_date": row.get("since_date", ""),
                        "age": row.get("age", ""),
                        "missed": row.get("missed", ""),
                    })

            logger.info("Transfermarkt: %d injuries for %s", len(injuries), team_name)
            return injuries
        except Exception as e:
            logger.warning("Transfermarkt Cloak error for %s: %s", team_name, e)
            return []

    def close(self):
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None


_scraper = TransfermarktCloakCollector()
get_team_injuries = _scraper.get_team_injuries
