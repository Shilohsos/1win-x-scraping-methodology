"""10x Betting — Main Orchestrator
Wires all layers together and runs the polling loop.
"""
import asyncio
import logging
import signal
import sys
from typing import Optional
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
                    # Calculate edge
                    opportunities = self.edge_calc.calculate(
                        match, odds, weather, ref_stats
                    )
                    for market_key, opp_data in opportunities.items():
                        opp_id = (
                            f"opp_{match.id}_{market_key}_"
                            f"{int(asyncio.get_event_loop().time())}"
                        )
                        opportunity = {
                            "id":    opp_id,
                            "match": match.to_dict(),
                            **opp_data,
                            "weather":       weather or {},
                            "referee_stats": ref_stats,
                        }
                        # Log to DB
                        await self.db.log_opportunity(opportunity)
                        # Send Telegram alert
                        await self.alerter.send_alert(opportunity)
                        edges_found += 1
                        # Rate limit alerts
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.error(
                        f"Match analysis error ({match.display_name()}): {e}"
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
