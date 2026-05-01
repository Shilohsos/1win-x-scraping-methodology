import logging
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
import re

logger = logging.getLogger("10xbet.twitter")

# Load last30days .env (credentials and proxy)
ENV_path = Path.home() / ".config" / "last30days" / ".env"
if ENV_path.exists():
    from dotenv import load_dotenv
    load_dotenv(str(ENV_path))
    logger.info("Loaded last30days .env (X credentials + proxy activated)")
else:
    logger.warning("last30days .env not found at %s", ENV_path)

# Add last30days scripts to path
SCRIPTS_DIR = Path.home() / ".hermes" / "skills" / "research" / "last30days" / "scripts"
if SCRIPTS_DIR.exists():
    sys.path.insert(0, str(SCRIPTS_DIR))
else:
    logger.error("last30days scripts dir missing: %s", SCRIPTS_DIR)

import lib.bird_x as _bx

class TwitterScraper:
    def __init__(self):
        self.auth_token = os.getenv("AUTH_TOKEN")
        self.ct0 = os.getenv("CT0")
        if self.auth_token and self.ct0:
            _bx.AUTH_TOKEN = self.auth_token
            _bx.CR_CSRF_TOKEN = self.ct0
            logger.info("X credentials loaded for bird_x")
        else:
            logger.warning("Missing AUTH_TOKEN or CT0 — X scraping may fail")
        logger.info("TwitterScraper ready (last30days/bird_x)")

    def get_sentiment(self, team_home: str, team_away: str) -> dict:
        topic = f"{team_home} {team_away}"
        now = datetime.now()
        try:
            result = _bx.search_x(
                topic=topic,
                from_date=(now - timedelta(days=30)).strftime("%Y-%m-%d"),
                to_date=now.strftime("%Y-%m-%d"),
                depth="default"
            )
            items = result.get("items") or []
            count = len(items)
            if count == 0:
                return {"score": 0.0, "posts": [], "count": 0}
        except Exception as e:
            logger.error("bird_x.search_x failed: %s", e)
            return {"score": 0.0, "posts": [], "count": 0, "error": str(e)}
        score = 0.0
        for item in items:
            text = item.get("text", "")
            sentiment = self._simple_sentiment(text)
            if sentiment > 0.1:
                score += 1
            elif sentiment < -0.1:
                score -= 1
        if count:
            score = score / count
        return {"score": round(score, 3), "posts": items, "count": count}

    def _simple_sentiment(self, text: str) -> float:
        pos = len(re.findall(r'\b(beat|win|great|amazing|victory|happy|good)\b', text, re.I))
        neg = len(re.findall(r'\b(lose|loss|terrible|awful|defeat|bad|worst)\b', text, re.I))
        total = pos + neg
        return (pos - neg) / total if total else 0.0

_scraper = TwitterScraper()
get_sentiment = _scraper.get_sentiment
