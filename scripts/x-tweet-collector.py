#!/usr/bin/env python3
"""
X/Twitter Real-Time Tweet Collector — Production Script

Collects real-time tweets discussing sports events without
official X API. Uses Scrapling + GraphQL endpoint.

Usage:
    python x-tweet-collector.py --query "Premier League today"
    python x-tweet-collector.py --queries-file queries.txt
"""
import sys, os, json, re, time, urllib.request
from datetime import datetime

COOKIE_FILE = os.path.expanduser('~/.config/last30days/.env')

def load_cookies():
    """Load X session cookies from last30days .env file."""
    cookies = {}
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    cookies[k.strip()] = v.strip()
    return {
        'auth_token': cookies.get('AUTH_TOKEN', ''),
        'ct0': cookies.get('CT0', ''),
    }

def discover_query_id():
    """Discover current SearchTimeline GraphQL query ID from X JS bundles."""
    bundle_urls = [
        'https://abs.twimg.com/responsive-web/client-web/main.js',
        'https://abs.twimg.com/responsive-web/client-web/vendor.js',
    ]
    for url in bundle_urls:
        try:
            response = urllib.request.urlopen(url, timeout=5)
            js = response.read().decode('utf-8', errors='ignore')
            matches = re.findall(
                r'SearchTimeline[^}]*?queryId:"([A-Za-z0-9_-]+)"', js
            )
            if matches:
                return matches[0]
        except:
            continue
    return None

def fetch_tweets(query, query_id, cookies, ct0, count=20):
    """Fetch tweets for a search query via GraphQL."""
    from scrapling import Fetcher
    
    fetcher = Fetcher()
    payload = {
        "variables": {
            "rawQuery": query,
            "count": count,
            "cursor": None,
            "querySource": "typed_query",
            "product": "Top"
        }
    }
    
    response = fetcher.post(
        url=f'https://twitter.com/i/api/graphql/{query_id}/SearchTimeline',
        json=payload,
        headers={
            'x-csrf-token': ct0,
            'x-twitter-active-user': 'yes',
            'x-twitter-client-language': 'en',
        },
        cookies=cookies,
    )
    return response.json()

def extract_tweets(resp_json):
    """Extract tweet objects from nested GraphQL response."""
    tweets = []
    timeline = (resp_json.get('data', {})
                .get('search_by_raw_query', {})
                .get('timeline', {}))
    for instruction in timeline.get('instructions', []):
        for entry in instruction.get('entries', []):
            item = entry.get('content', {}).get('item', {})
            tweet = item.get('tweet')
            if tweet:
                tweets.append(tweet)
    return tweets

def collect_tweets(queries, delay=10):
    """Collect tweets for multiple search queries."""
    cookies = load_cookies()
    ct0 = cookies.get('ct0', '')
    query_id = discover_query_id()
    
    if not query_id:
        print("ERROR: Could not discover query ID", file=sys.stderr)
        return []
    
    all_tweets = []
    seen_ids = set()
    
    for query in queries:
        print(f"  Fetching: '{query}'...")
        try:
            data = fetch_tweets(query, query_id, cookies, ct0)
            tweets = extract_tweets(data)
            
            for t in tweets:
                tid = t.get('rest_id')
                if tid and tid not in seen_ids:
                    seen_ids.add(tid)
                    all_tweets.append(t)
            
            print(f"    Got {len(tweets)} tweets, {len(all_tweets)} unique so far")
        except Exception as e:
            print(f"    Error: {e}")
        
        time.sleep(delay)
    
    return all_tweets

if __name__ == '__main__':
    queries = sys.argv[1:] if len(sys.argv) > 1 else [
        "Premier League fixtures today",
    ]
    
    print(f"Collecting tweets for {len(queries)} queries...")
    tweets = collect_tweets(queries)
    
    output_file = f"/tmp/x_tweets_{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(tweets, f, indent=2)
    
    print(f"\nSaved {len(tweets)} tweets to {output_file}")
