"""
FlashscoreCloakCollector — CloakBrowser-based replacement.
Delegates to FootballDataCollector (football-data.org API) for head-to-head stats.
Interface: get_h2h(home_team, away_team) -> Dict[str, Any]
"""
import os, logging, re
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    import sys
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from collectors.footballdata_cloak import FootballDataCollector
    _FD_AVAILABLE = True
except Exception:
    _FD_AVAILABLE = False
    FootballDataCollector = None

class FlashscoreCloakCollector:
    """
    Provides H2H head-to-head records from Football-Data.org API.
    Drop-in replacement: get_h2h(home_team, away_team) -> dict
    """
    def __init__(self):
        self._client = None
        if _FD_AVAILABLE:
            try:
                self._client = FootballDataCollector()
                logger.info("FlashscoreCloakCollector → FootballData.org (API)")
            except Exception as e:
                logger.warning(f"FlashscoreCloak init failed: {e}")
        else:
            logger.warning("FlashscoreCloak: FootballDataCollector not available; operations will fail")

    def get_h2h(self, home_team: str, away_team: str) -> Dict[str, Any]:
        """
        Fetch H2H between two teams via Football-Data.org.
        Returns typical keys: team_a_wins, team_b_wins, draws, last5 (list), total_matches
        """
        if self._client is None:
            logger.error("FlashscoreCloakCollector: no client available")
            return {"error": "client unavailable", "team_a_wins": 0, "team_b_wins": 0, "draws": 0, "last5": []}

        try:
            return self._client.get_h2h(home_team, away_team)
        except Exception as e:
            logger.warning("FlashscoreCloak H2H error (%s vs %s): %s", home_team, away_team, e)
            return {"error": str(e), "team_a_wins": 0, "team_b_wins": 0, "draws": 0, "last5": []}

    def close(self):
        """No-op for API client; kept for interface compatibility."""
        pass

# Singleton
_scraper = FlashscoreCloakCollector()
get_h2h = _scraper.get_h2h
