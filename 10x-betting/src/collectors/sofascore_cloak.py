"""
SofascoreCloakCollector — CloakBrowser-based replacement.
Currently delegates to FootballDataCollector (football-data.org API) due to
Sofascore bot detection issues in headless environments.
Maintains interface compatibility: get_team_form(team_name) -> dict | None
"""
import os, logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Optional: import FootballDataCollector; if missing, raise friendly
try:
    import sys, json
    # Ensure project root on path for env loading
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from collectors.footballdata_cloak import FootballDataCollector
    _FD_AVAILABLE = True
except Exception:
    _FD_AVAILABLE = False
    FootballDataCollector = None

class SofascoreCloakCollector:
    """
    Provides recent match form using Football-Data.org API.
    This is a drop-in replacement for the historical Sofascore browser scraper.
    """
    def __init__(self):
        self._client = None
        if _FD_AVAILABLE:
            try:
                self._client = FootballDataCollector()
                logger.info("SofascoreCloakCollector → FootballData.org (API)")
            except Exception as e:
                logger.warning(f"SofascoreCloak: failed to init API client: {e}")
        else:
            logger.warning("SofascoreCloak: FootballDataCollector not available; operations will fail")

    def get_team_form(self, team_name: str) -> Optional[Dict[str, Any]]:
        """Return last-5 match form for the team."""
        if self._client is None:
            logger.error("SofascoreCloakCollector: no client available (check dependencies)")
            return None
        try:
            return self._client.get_team_form(team_name)
        except Exception as e:
            logger.warning("SofascoreCloak error (%s): %s", team_name, e)
            return None

# Singleton for module-level usage (eponymous pattern)
_scraper = SofascoreCloakCollector()
get_team_form = _scraper.get_team_form
