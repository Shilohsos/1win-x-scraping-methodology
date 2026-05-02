#!/usr/bin/env python3
"""
LiveScore API Scraper — Production Script

Fetches fixtures for a given date from LiveScore's public API.
No authentication, no proxy, no browser required.

Usage:
  python scrape_livescore.py --date 20260503 --format json
  python scrape_livescore.py --date today --output matches.jsonl

Output formats:
  - json: Pretty-printed full JSON (default)
  - jsonl: One event per line (for streaming)
  - table: Human-readable table
  - csv: CSV to stdout

Examples:
  # Get tomorrow's fixtures as JSON
  python scrape_livescore.py --date "$(date -d '+1 day' +%Y%m%d)" --format json

  # Get today's fixtures as CSV for spreadsheet import
  python scrape_livescore.py --date "$(date +%Y%m%d)" --format csv > today.csv

  # Find all Premier League matches
  python scrape_livescore.py --date 20260503 --format json | jq '.Stages[] | select(.Snm=="Premier League") | .Events'
"""

import argparse
import json
import sys
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any

# ─── Configuration ──────────────────────────────────────────────────────────────

BASE_URL = "https://prod-cdn-mev-api.livescore.com/v1/api/app/date/soccer/{date}/2"
DEFAULT_PARAMS = {
    "countryCode": "GB",   # filters display order; all data still returned
    "locale": "en"
}
TIMEOUT = 15  # seconds
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ─── Helpers ────────────────────────────────────────────────────────────────────

def date_str_to_api(datestr: str) -> str:
    """Convert YYYY-MM-DD or YYYYMMDD to API format (YYYYMMDD)."""
    datestr = datestr.replace("-", "")
    if len(datestr) != 8 or not datestr.isdigit():
        raise ValueError("date must be YYYY-MM-DD or YYYYMMDD")
    return datestr

def resolve_date(datestr: str) -> str:
    """Resolve 'today', 'tomorrow', or explicit date to YYYYMMDD."""
    if datestr.lower() == "today":
        return datetime.now().strftime("%Y%m%d")
    if datestr.lower() == "tomorrow":
        return (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
    return date_str_to_api(datestr)

def fetch_livescore(date_str: str) -> Dict[str, Any]:
    """Fetch raw JSON from LiveScore API."""
    url = BASE_URL.format(date=date_str)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Referer": "https://www.livescore.com/"
    }

    resp = requests.get(url, params=DEFAULT_PARAMS, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def parse_events(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten nested response into a list of event dicts with key fields."""
    events = []
    for stage in data.get("Stages", []):
        comp_name = stage.get("Snm", "Unknown")
        country = stage.get("Cnm", "?")
        comp_id = stage.get("CompId", "?")
        for evt in stage.get("Events", []):
            # Team data: T1=home, T2=away (each is a list[dict])
            t1 = evt.get("T1", [{}])[0]
            t2 = evt.get("T2", [{}])[0]

            # Kickoff as integer YYYYMMDDHHMMSS → formatted string
            raw_kickoff = evt.get("Esd", "")
            kickoff = ""
            if raw_kickoff and len(str(raw_kickoff)) == 14:
                try:
                    kickoff = datetime.strptime(str(raw_kickoff), "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    kickoff = str(raw_kickoff)

            events.append({
                "event_id": evt.get("Eid"),
                "competition": comp_name,
                "competition_id": comp_id,
                "country": country,
                "home_team": t1.get("Nm", ""),
                "home_abbr": t1.get("Abr", ""),
                "home_id": t1.get("ID", ""),
                "away_team": t2.get("Nm", ""),
                "away_abbr": t2.get("Abr", ""),
                "away_id": t2.get("ID", ""),
                "home_score": evt.get("Tr1"),
                "away_score": evt.get("Tr2"),
                "status": evt.get("Eps", ""),
                "status_id": evt.get("Esid"),
                "kickoff": kickoff,
                "kickoff_raw": raw_kickoff,
                "provider_ids": evt.get("Pids", {}),
                "external_ids": {
                    "live_score_extra": evt.get("EO"),
                    "live_score_extra_x": evt.get("EOX"),
                    "sport_id": evt.get("Spid"),
                    "provider_id": evt.get("Pid"),
                },
            })
    return events

def filter_events(events: List[Dict[str, Any]],
                  comp: str = None,
                  country: str = None,
                  status: str = None,
                  team: str = None) -> List[Dict[str, Any]]:
    """Filter events by competition, country, status, or team substring."""
    filtered = events
    if comp:
        filtered = [e for e in filtered if comp.lower() in e["competition"].lower()]
    if country:
        filtered = [e for e in filtered if country.lower() in e["country"].lower()]
    if status:
        filtered = [e for e in filtered if status.upper() == e["status"].upper()]
    if team:
        filtered = [e for e in filtered if
                    team.lower() in e["home_team"].lower() or
                    team.lower() in e["away_team"].lower()]
    return filtered

# ─── Output Formatters ─────────────────────────────────────────────────────────

def format_json(events: List[Dict], pretty: bool = True) -> str:
    if pretty:
        return json.dumps({"events": events, "count": len(events)}, indent=2)
    return json.dumps({"events": events, "count": len(events)})

def format_jsonl(events: List[Dict]) -> str:
    lines = [json.dumps(e, separators=(",", ":")) for e in events]
    return "\n".join(lines)

def format_table(events: List[Dict]) -> str:
    lines = []
    header = f"{'Kickoff':<16} {'Competition':<30} {'Home':<25} {'Score':>6} {'Away':<25} {'Status':<5}"
    lines.append(header)
    lines.append("-" * len(header))
    for e in events:
        score = f"{e['home_score']}-{e['away_score']}" if e['home_score'] is not None else "vs"
        line = (f"{e['kickoff']:<16} {e['competition']:<30} "
                f"{e['home_team']:<25} {score:>6} {e['away_team']:<25} {e['status']:<5}")
        lines.append(line)
    return "\n".join(lines)

def format_csv(events: List[Dict]) -> str:
    if not events:
        return ""
    # Header
    fieldnames = [
        "event_id", "competition", "competition_id", "country",
        "home_team", "home_abbr", "home_id",
        "away_team", "away_abbr", "away_id",
        "home_score", "away_score", "status", "status_id",
        "kickoff", "kickoff_raw"
    ]
    lines = [",".join(fieldnames)]
    for e in events:
        row = [str(e.get(f, "")) for f in fieldnames]
        lines.append(",".join(row))
    return "\n".join(lines)

# ─── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch football fixtures from LiveScore API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--date", default="today",
                        help="Date to fetch: YYYY-MM-DD, YYYYMMDD, 'today', or 'tomorrow' (default: today)")
    parser.add_argument("--format", choices=["json", "jsonl", "table", "csv"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--output", "-o", type=str,
                        help="Write output to file instead of stdout")
    parser.add_argument("--competition", "-c", type=str,
                        help="Filter by competition name (substring match, case-insensitive)")
    parser.add_argument("--country", type=str,
                        help="Filter by country name (substring match)")
    parser.add_argument("--status", "-s", type=str,
                        help="Filter by status (NS, LIVE, FT, HT, etc.)")
    parser.add_argument("--team", "-t", type=str,
                        help="Filter by team name (home OR away)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress progress messages to stderr")

    args = parser.parse_args()

    # Resolve date
    try:
        date_api = resolve_date(args.date)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"[*] Fetching LiveScore data for {args.date} ({date_api})...", file=sys.stderr)

    # Fetch
    try:
        raw = fetch_livescore(date_api)
    except requests.HTTPError as e:
        print(f"Error: HTTP {e.response.status_code} from LiveScore API", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Error: Network failure — {e}", file=sys.stderr)
        sys.exit(1)

    # Parse
    events = parse_events(raw)
    if not args.quiet:
        print(f"[+] Retrieved {len(events)} events across {len(raw.get('Stages', []))} competitions", file=sys.stderr)

    # Filter
    filtered = filter_events(
        events,
        comp=args.competition,
        country=args.country,
        status=args.status,
        team=args.team
    )
    if not args.quiet:
        print(f"[+] After filtering: {len(filtered)} events", file=sys.stderr)

    # Format
    if args.format == "json":
        output = format_json(filtered, pretty=True)
    elif args.format == "jsonl":
        output = format_jsonl(filtered)
    elif args.format == "table":
        output = format_table(filtered)
    elif args.format == "csv":
        output = format_csv(filtered)
    else:
        output = format_json(filtered)

    # Write
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output + ("\n" if args.format != "json" else ""))
        if not args.quiet:
            print(f"[+] Saved to {args.output} ({len(filtered)} events)", file=sys.stderr)
    else:
        print(output)

if __name__ == "__main__":
    main()
