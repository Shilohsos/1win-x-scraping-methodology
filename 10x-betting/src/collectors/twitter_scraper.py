import requests
import logging
from bs4 import BeautifulSoup
from textblob import TextBlob

logger = logging.getLogger("10xbet.twitter")

NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
    "https://nitter.rawbit.ninja",
    "https://nitter.mint.lgbt",
    "https://nitter.esmailelbob.xyz",
    "https://nitter.tiekoetter.com",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; Infinix X6816D) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/112.0.0.0 Mobile Safari/537.36"
    )
}

class TwitterScraper:
    def __init__(self):
        logger.info("TwitterScraper ready (Nitter proxy mode)")

    def get_sentiment(self, team_home, team_away):
        query = f"{team_home} {team_away}"
        tweets = []
        for instance in NITTER_INSTANCES:
            try:
                encoded = requests.utils.quote(query)
                url = f"{instance}/search?q={encoded}&f=tweets"
                r = requests.get(url, headers=HEADERS, timeout=10)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "lxml")
                tweet_divs = (
                    soup.find_all("div", class_="tweet-content")
                    or soup.find_all("div", class_="content")
                )
                for div in tweet_divs[:15]:
                    text = div.get_text(strip=True)
                    if text and len(text) > 10:
                        score = TextBlob(text).sentiment.polarity
                        tweets.append({"text": text[:200], "score": score})
                if tweets:
                    break
            except Exception as e:
                logger.warning("Nitter instance %s failed: %s", instance, e)

        avg = sum(t["score"] for t in tweets) / len(tweets) if tweets else 0
        logger.info(
            "Twitter sentiment %s vs %s: %.2f (%d tweets)",
            team_home, team_away, avg, len(tweets)
        )
        return {"score": avg, "tweets": tweets, "count": len(tweets)}
