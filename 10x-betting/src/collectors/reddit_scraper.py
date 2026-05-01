import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
import re

logger = logging.getLogger("10xbet.reddit")

# Load last30days .env to activate proxy and credentials
ENV_path = Path.home() / ".config" / "last30days" / ".env"
if ENV_path.exists():
    from dotenv import load_dotenv
    load_dotenv(str(ENV_path))
    logger.info("Loaded last30days .env (proxy/credentials activated)")
else:
    logger.warning("last30days .env not found at %s", ENV_path)

# Add last30days scripts to Python path
SCRIPTS_DIR = Path.home() / ".hermes" / "skills" / "research" / "last30days" / "scripts"
if SCRIPTS_DIR.exists():
    sys.path.insert(0, str(SCRIPTS_DIR))
else:
    logger.error("last30days scripts dir missing: %s", SCRIPTS_DIR)

# Override reddit_public UA to avoid 403
import lib.reddit_public as _rp
_rp.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
logger.info("Reddit UA overridden")

class RedditScraper:
    def __init__(self):
        self.subreddits = ["soccer", "PremierLeague", "football"]
        logger.info("RedditScraper ready (last30days/reddit_public + browser UA)")

    def get_sentiment(self, team_home: str, team_away: str) -> dict:
        topic = f"{team_home} {team_away}"
        now = datetime.now()
        results = _rp.search_reddit_public(
            topic=topic,
            from_date=(now - timedelta(days=90)).strftime("%Y-%m-%d"),
            to_date=now.strftime("%Y-%m-%d"),
            depth="default",
            subreddits=self.subreddits,
        )
        count = len(results)
        score = 0.0
        for item in results:
            text = f"{item.get('title','')} {item.get('body','')}"
            sentiment = self._simple_sentiment(text)
            if sentiment > 0.1:
                score += 1
            elif sentiment < -0.1:
                score -= 1
        if count:
            score = score / count
        return {"score": round(score, 3), "posts": results, "count": count}

    def _simple_sentiment(self, text: str) -> float:
        pos = len(re.findall(r'\b(love|win|great|excellent|victory|happy|comeback)\b', text, re.I))
        neg = len(re.findall(r'\b(lose|loss|terrible|awful|defeat|bad| pathetic)\b', text, re.I))
        total = pos + neg
        if total == 0:
            return 0.0
        return (pos - neg) / total

_scraper = RedditScraper()
get_sentiment = _scraper.get_sentiment
