"""10x Betting — Main Orchestrator
Wires all layers together and runs the polling loop.
"""
import asyncio
import logging
import signal
import sys
from typing import Optional, Dict
from src.utils.logger import setup_logging
from src.utils.config import config
from src.storage.db import Database
from src.models.edge import EdgeCalculator
from src.collectors.fixtures import FixturesCollector
from src.collectors.weather import WeatherCollector
from src.collectors.referees import RefereeDB
from src.collectors.odds import OddsCollector
from src.alerts.telegram import TelegramAlerter
from src.alerts.executor import BetExecutor

from src.collectors.news import NewsCollector
from src.collectors.reddit_scraper import RedditScraper
from src.collectors.twitter_scraper import TwitterScraper
from src.collectors.transfermarkt import TransfermarktCollector
from src.collectors.official_sites import OfficialSitesCollector
from src.collectors.physioroom import PhysioroomCollector
from src.collectors.flashscore import FlashscoreCollector
from src.collectors.oddschecker import OddscheckerCollector
from src.models.signal_engine import SignalEngine
from src.models.edge import EdgeCalculator
import time
from datetime import datetime, timezone
setup_logging()
logger = logging.getLogger("10xbet.main")

LEAGUES = ["PL", "CL", "PD"]  # EPL, UCL, La Liga — SportyBet Nigeria coverage

class TenXBetting:
    def __init__(self):
        self.db:         Optional[Database]         = None
        self.fixtures:   Optional[FixturesCollector] = None
        self.weather:    Optional[WeatherCollector]  = None
        self.referee_db: Optional[RefereeDB]         = None
        self.edge_calc:  Optional[EdgeCalculator]    = None
        self.odds:       Optional[OddsCollector]     = None
        self.executor:   Optional[BetExecutor]       = None
        self.alerter:    Optional[TelegramAlerter]   = None
        self.running:    bool                        = False

        # Multi-source scrapers (initialized in init_scrapers)
        self._news_collector:      Optional[NewsCollector]      = None
        self._reddit_scraper:      Optional[RedditScraper]      = None
        self._twitter_scraper:     Optional[TwitterScraper]     = None
        self._transfermarkt:       Optional[TransfermarktCollector] = None
        self._official_sites:      Optional[OfficialSitesCollector] = None
        self._physioroom:          Optional[PhysioroomCollector]   = None
        self._flashscore:          Optional[FlashscoreCollector]   = None
        self._oddschecker:         Optional[OddscheckerCollector]  = None
        self._signal_engine:       Optional[SignalEngine]         = None
        self._edge_calc_new:       Optional[EdgeCalculator]       = None
        # Scheduler state
        self._last_sentiment_scrape: float = 0
        self._last_form_scrape:      float = 0
        self._last_deep_scrape:      float = 0
        self._last_daily_scrape:     float = 0
        # In-memory caches for scraped data (keyed by team name or tuple)
        self._team_form_cache:   Dict = {}
        self._injuries_cache:    Dict = {}
        self._h2h_cache:         Dict = {}
        self._sentiment_cache:   Dict = {}
        self._player_form_cache: Dict = {}

    async def initialize(self):
        logger.info("═══════════════════════════════════")
        logger.info("   10X BETTING ORACLE — STARTING   ")
        logger.info("═══════════════════════════════════")
        # Layer 1: Database
        self.db = Database()
        await self.db.initialize()
        logger.info("✓ Database ready")
        # Layer 2: Collectors
        self.fixtures = FixturesCollector(
            api_key=config.get("football_data.api_key")
        )
        self.weather = WeatherCollector(
            api_key=config.get("openweathermap.api_key")
        )
        self.referee_db = RefereeDB(self.db)
        self.edge_calc  = EdgeCalculator(self.referee_db)
        logger.info("✓ Collectors ready")
        # Layer 3: 1win browser
        self.odds = OddsCollector(
            username=config.get("1win.username"),
            password=config.get("1win.password"),
            headless=config.get("1win.headless", True),
        )
        await self.odds.start()
        logged_in = await self.odds.login()
        if not logged_in:
            logger.warning(
                "⚠ 1win login failed — odds scraping will be limited. "
                "Check debug/odds/ for screenshots."
            )
        else:
            logger.info("✓ 1win browser session ready")
        # Layer 4: Bet executor
        self.executor = BetExecutor(odds_collector=self.odds)
        logger.info("✓ Bet executor ready")
        # Layer 5: Telegram bot
        self.alerter = TelegramAlerter(bet_executor=self.executor)
        await self.alerter.initialize()
        logger.info("✓ Telegram bot ready")
        logger.info("═══════════════════════════════════")
        logger.info("   ALL SYSTEMS GO — POLLING LIVE   ")

        # Initialise multi-source scrapers and signal engine
        await self.init_scrapers()

    async def init_scrapers(self):
        """Initialise all scraper instances once at startup."""
        logger.info("Initialising scraper instances...")
        self._news_collector     = NewsCollector()
        self._reddit_scraper     = RedditScraper()
        self._twitter_scraper    = TwitterScraper()
        self._transfermarkt      = TransfermarktCollector()
        self._official_sites     = OfficialSitesCollector()
        self._physioroom         = PhysioroomCollector()
        self._flashscore         = FlashscoreCollector()
        self._oddschecker        = OddscheckerCollector()
        self._signal_engine      = SignalEngine()
        # Reuse existing self.edge_calc (new EdgeCalculator class already loaded)
        # but we need the new interface; ensure we are using the updated EdgeCalculator.
        self._edge_calc_new      = self.edge_calc
        logger.info("All scrapers initialised")

    @staticmethod
    def should_run(last_run: float, interval: int) -> bool:
        return (time.time() - last_run) >= interval

    async def run_sentiment_scrape(self, fixtures):
        """Run every 30 min — news, reddit, twitter sentiment."""
        logger.info("Running sentiment scrape (%d fixtures)...", len(fixtures))
        for fixture in fixtures[:10]:  # limit to avoid rate limiting
            home = fixture.home_team
            away = fixture.away_team
            key = (home, away)
            try:
                news_res  = self._news_collector.get_sentiment(home, away)
                reddit_res= self._reddit_scraper.get_sentiment(home, away)
                twitter_res = self._twitter_scraper.get_sentiment(home, away)
                self._sentiment_cache[key] = {
                    "news":   {"score": news_res.get("score",0),   "count": news_res.get("count",0)},
                    "reddit": {"score": reddit_res.get("score",0), "count": reddit_res.get("count",0)},
                    "twitter":{"score": twitter_res.get("score",0),"count": twitter_res.get("count",0)},
                }
            except Exception as e:
                logger.warning("Sentiment scrape error %s vs %s: %s", home, away, e)
        self._last_sentiment_scrape = time.time()
        logger.info("Sentiment scrape complete")

    async def run_form_scrape(self, fixtures):
        """Run every 3 hours — player form, injuries, official sites."""
        logger.info("Running form scrape...")
        teams_done = set()
        for fixture in fixtures:
            for team in [fixture.home_team, fixture.away_team]:
                if team in teams_done:
                    continue
                teams_done.add(team)
                try:
                    # Sofascore team form
                    form = self._flashscore.get_team_form(team)
                    if form:
                        self._team_form_cache[team] = form
                    # Injuries
                    injuries_physio = self._physioroom.get_injuries(team)
                    injuries_tm = self._transfermarkt.get_team_injuries(team)
                    # Combine
                    all_inj = (injuries_physio or []) + (injuries_tm or [])
                    self._injuries_cache[team] = all_inj
                    # Official sites headlines (not used in evaluation currently)
                    headlines = self._official_sites.get_team_news(team)
                    # Could store if needed; skipping for now
                except Exception as e:
                    logger.warning("Form scrape error %s: %s", team, e)
        self._last_form_scrape = time.time()
        logger.info("Form scrape complete — %d teams", len(teams_done))

    async def run_deep_scrape(self, fixtures):
        """Run every 6 hours — H2H, oddschecker."""
        logger.info("Running deep scrape...")
        for fixture in fixtures:
            try:
                home, away = fixture.home_team, fixture.away_team
                h2h = self._flashscore.get_h2h(home, away)
                self._h2h_cache[(home, away)] = h2h
                # Oddschecker sentiment not currently used in signal engine
                # self._oddschecker.get_market_sentiment(home, away)
            except Exception as e:
                logger.warning("Deep scrape error: %s", e)
        self._last_deep_scrape = time.time()
        logger.info("Deep scrape complete")
        logger.info("═══════════════════════════════════")

    async def run_cycle(self):
        """One full polling cycle: fetch → analyse → alert."""
        logger.info("── Cycle start ──")
        try:
            matches = await self.fixtures.fetch_upcoming(
                LEAGUES, hours_ahead=120
            )
            if not matches:
                logger.warning("No upcoming matches found")
                return

            # Multi-frequency scheduler: run scrapers if interval elapsed
            if self.should_run(self._last_sentiment_scrape, 1800):
                await self.run_sentiment_scrape(matches)
            if self.should_run(self._last_form_scrape, 10800):
                await self.run_form_scrape(matches)
            if self.should_run(self._last_deep_scrape, 21600):
                await self.run_deep_scrape(matches)
            edges_found = 0
            edges_found = 0
            for match in matches[:25]:  # Cap per cycle
                try:
                    # Save match to DB
                    await self.db.upsert_match(match)
                    # Get odds from 1win
                    odds = await self.odds.get_match_odds(match)
                    if not odds:
                        continue
                    # Get weather
                    weather = await self.weather.get(
                        match.latitude, match.longitude
                    ) if match.latitude and match.longitude else None
                    # Get referee stats
                    ref_stats = await self.referee_db.get_stats(
                        match.referee_id or ""
                    )
                    # --- NEW: Gather scraped data from caches ---
                    home = match.home_team
                    away = match.away_team
                    team_form = {
                        "home": self._team_form_cache.get(home, {}),
                        "away": self._team_form_cache.get(away, {}),
                    }
                    injuries = {
                        "home": self._injuries_cache.get(home, []),
                        "away": self._injuries_cache.get(away, []),
                    }
                    h2h_data = self._h2h_cache.get((home, away), {})
                    sentiment_data = self._sentiment_cache.get((home, away), {})
                    player_form = {}   # Not yet scraped
                    standings = None   # Not yet scraped
                    # Evaluate all signal groups
                    signal_eval = self._signal_engine.evaluate(
                        fixture=match,
                        odds=odds,
                        weather=weather,
                        referee=ref_stats,
                        team_form=team_form,
                        h2h=h2h_data,
                        injuries=injuries,
                        sentiment=sentiment_data,
                        player_form=player_form,
                        standings=standings,
                    )
                    # Calculate edge per market using new engine
                    opportunities = self._edge_calc_new.calculate_all(
                        odds_dict=odds,
                        signal_eval=signal_eval,
                        weather=weather,
                        team_form=team_form,
                        h2h=h2h_data,
                    )
                    for opp in opportunities:
                        if not signal_eval.get("should_alert"):
                            continue
                        opp_id = f"opp_{match.id}_{opp['market_key']}_{int(asyncio.get_event_loop().time())}"
                        opportunity = {
                            "id": opp_id,
                            "match": match.to_dict(),
                            **opp,
                            "weather": weather or {},
                            "referee_stats": ref_stats,
                            "edge_result": opp,
                            "signal_eval": signal_eval,
                        }
                        await self.db.log_opportunity(opportunity)
                        await self.alerter.send_alert(opportunity)
                        edges_found += 1
                        await asyncio.sleep(1)

                except Exception:
                    logger.exception(
                        f"Match analysis error ({match.display_name()})"
                    )
                    continue
            logger.info(
                f"── Cycle complete: {edges_found} edges "
                f"from {len(matches)} matches ──"
            )
        except Exception as e:
            logger.error(f"Cycle error: {e}", exc_info=True)

    async def scheduler(self):
        """Main polling loop."""
        interval = config.get("scheduler.poll_interval", 300)
        logger.info(f"Scheduler: polling every {interval}s")
        while self.running:
            await self.run_cycle()
            logger.info(f"Sleeping {interval}s...")
            await asyncio.sleep(interval)

    async def shutdown(self):
        logger.info("Shutting down 10x Betting...")
        self.running = False
        if self.odds:
            await self.odds.stop()
        if self.alerter:
            await self.alerter.shutdown()
        logger.info("Shutdown complete")

async def main():
    system = TenXBetting()
    loop = asyncio.get_event_loop()
    def _sig_handler():
        logger.info("Signal received — shutting down...")
        asyncio.create_task(system.shutdown())
    loop.add_signal_handler(signal.SIGINT,  _sig_handler)
    loop.add_signal_handler(signal.SIGTERM, _sig_handler)
    try:
        await system.initialize()
        system.running = True
        await system.scheduler()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        await system.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
