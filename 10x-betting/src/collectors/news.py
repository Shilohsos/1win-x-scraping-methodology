import feedparser
import logging
from textblob import TextBlob

logger = logging.getLogger("10xbet.news")

RSS_FEEDS = {
    "bbc_sport":       "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "sky_sports":      "https://www.skysports.com/rss/12040",
    "goal_com":        "https://www.goal.com/feeds/en/news",
    "guardian":        "https://www.theguardian.com/football/rss",
    "espn_fc":         "https://www.espn.com/espn/rss/soccer/news",
    "football365":     "https://www.football365.com/feed",
}

class NewsCollector:
    def __init__(self):
        logger.info("NewsCollector ready — %d feeds", len(RSS_FEEDS))

    def get_sentiment(self, team_home, team_away):
        results = []
        keywords = [
            team_home.lower(),
            team_away.lower(),
            team_home.split()[0].lower(),
            team_away.split()[0].lower(),
        ]
        for source, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:20]:
                    title = entry.get("title", "").lower()
                    summary = entry.get("summary", "").lower()
                    text = title + " " + summary
                    if any(kw in text for kw in keywords):
                        blob = TextBlob(entry.get("title", ""))
                        score = blob.sentiment.polarity
                        results.append({
                            "source": source,
                            "headline": entry.get("title", ""),
                            "score": score,
                            "published": entry.get("published", ""),
                        })
            except Exception as e:
                logger.warning("Feed error %s: %s", source, e)

        avg = sum(r["score"] for r in results) / len(results) if results else 0
        logger.info(
            "News sentiment %s vs %s: %.2f (%d articles)",
            team_home, team_away, avg, len(results)
        )
        return {"score": avg, "articles": results, "count": len(results)}
