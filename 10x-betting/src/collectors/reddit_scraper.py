import requests
import logging
from textblob import TextBlob

logger = logging.getLogger("10xbet.reddit")

SUBREDDITS = ["soccer", "PremierLeague", "laliga", "footballhighlights"]
HEADERS = {"User-Agent": "Mozilla/5.0 10xBettingBot/1.0"}

class RedditScraper:
    def __init__(self):
        logger.info("RedditScraper ready")

    def get_sentiment(self, team_home, team_away):
        results = []
        keywords = [
            team_home.lower(),
            team_away.lower(),
            team_home.split()[0].lower(),
            team_away.split()[0].lower(),
        ]
        for sub in SUBREDDITS:
            try:
                url = f"https://www.reddit.com/r/{sub}/search.json"
                query = f"{team_home} {team_away}"
                r = requests.get(
                    url,
                    headers=HEADERS,
                    params={
                        "q": query,
                        "limit": 10,
                        "sort": "new",
                        "restrict_sr": 1,
                    },
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                posts = r.json().get("data", {}).get("children", [])
                for post in posts:
                    d = post.get("data", {})
                    title = d.get("title", "")
                    if any(kw in title.lower() for kw in keywords):
                        score = TextBlob(title).sentiment.polarity
                        upvotes = d.get("ups", 0)
                        results.append({
                            "subreddit": sub,
                            "title": title,
                            "score": score,
                            "upvotes": upvotes,
                        })
            except Exception as e:
                logger.warning("Reddit error r/%s: %s", sub, e)

        weighted = sum(r["score"] * max(r["upvotes"], 1) for r in results)
        total_votes = sum(max(r["upvotes"], 1) for r in results) if results else 1
        avg = weighted / total_votes if results else 0
        logger.info(
            "Reddit sentiment %s vs %s: %.2f (%d posts)",
            team_home, team_away, avg, len(results)
        )
        return {"score": avg, "posts": results, "count": len(results)}
