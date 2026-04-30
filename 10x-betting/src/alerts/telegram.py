"""
10x Betting — Telegram Alerter (Manual Mode)
Sends edge alerts with 1win navigation instructions.
Shiloh places bets manually on his phone.
PLACED button logs the bet to DB for P&L tracking.
"""
import logging
from datetime import datetime
from typing import Dict, Optional


from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
      Application,
      CallbackQueryHandler,
      CommandHandler,
      ContextTypes,
)


from src.utils.config import config
from src.models.market import get_market
from src.storage.db import Database


logger = logging.getLogger("10xbet.telegram")


# Stake recommendation by edge size
STAKE_TIERS = [
    (20.0, 2000),      # edge >= 20% → ₦2000
    (15.0, 1000),      # edge >= 15% → ₦1000
    (12.0, 500),       # edge >= 12% → ₦500
]


# 1win league navigation paths
LEAGUE_PATHS = {
    "PL": "Football → England → Premier League",
    "CL": "Football → Europe → Champions League",
    "PD": "Football → Spain → La Liga",
}


# 1win navigation instructions per market
# These match what Shiloh will see on 1win.ng
MARKET_TABS = {
    "total_over_25":   "Total section → Over 2.5",
    "total_over_35":   "Total section → Over 3.5",
    "btts_yes":        "Total and both teams to score → Over 2.5 And Yes",
    "win_either_half": "To win either half → [team name]",
    "to_win_to_nil":   "To win to nil → [team name]",
    "corners_over":    "Corners. Total → Over 10.5",
    "1h_total_over":   "Halves tab → 1st half. Total → Over 0.5",
    "draw_and_over":   "Result and total → Draw And Over 2.5",
}


def _esc(text: str) -> str:
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _recommended_stake(edge_pct: float) -> int:
    for threshold, stake in STAKE_TIERS:
        if edge_pct >= threshold:
            return stake
    return 500



class TelegramAlerter:
    def __init__(self, bet_executor=None):
        # bet_executor ignored in manual mode
        self.chat_id = config.get("telegram.chat_id")
        self.app: Optional[Application] = None
        self.pending: Dict[str, Dict] = {}
        self.db = Database()


    async def initialize(self):
        token = config.get("telegram.bot_token")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

        self.app = Application.builder().token(token).build()
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("stats", self._cmd_stats))
        self.app.add_handler(CommandHandler("pending", self._cmd_pending))
        self.app.add_handler(CallbackQueryHandler(self._on_button))

        await self.app.initialize()
        await self.app.start()
        await self.db.initialize()

        me = await self.app.bot.get_me()
        logger.info(f"Telegram bot @{me.username} online")


    def _format_signal_alert(self, fixture, market_key, odds,
                             edge_result, signal_eval,
                             market_instruction=""):
        """Build the new multi-signal alert message."""
        home = fixture.get("home_team") if isinstance(fixture, dict) else getattr(fixture, "home_team", "Unknown")
        away = fixture.get("away_team") if isinstance(fixture, dict) else getattr(fixture, "away_team", "Unknown")
        league = fixture.get("league") if isinstance(fixture, dict) else getattr(fixture, "competition", "Football")
        kickoff = fixture.get("kickoff") if isinstance(fixture, dict) else getattr(fixture, "kickoff", None)
        match_time = (datetime.fromisoformat(kickoff.replace("Z", "+00:00")).strftime("%d %b") if kickoff else "TBD")

        confidence = "HIGH CONFIDENCE" if signal_eval.get("high_confidence") else "MEDIUM CONFIDENCE"
        stake_level = signal_eval.get("stake_level", "LOW      ")
        edge_pct = edge_result.get("edge_pct", 0)
        implied = edge_result.get("implied_prob", 0) * 100
        our_prob = edge_result.get("our_prob", 0) * 100

        # Build signal lines
        signal_lines = []
        groups = signal_eval.get("groups", [])
        for group in groups:
            if group.name == "Availability":
                icon = "⏺️ "
            elif group.active:
                icon = "🟢 "
            else:
                icon = "⚪️ "
            signal_lines.append(f"{icon} {group.name} — {group.reason}")

        signals_text = "\n".join(signal_lines)

        nav = f"\nFIND ON 1WIN: {market_instruction}" if market_instruction else ""

        msg = (
            f"    EDGE DETECTED — {confidence}\n\n"
            f"{home} vs {away}\n"
            f"{league} | {match_time}\n\n"
            f"Market: {market_key.replace('_', ' ').title()}\n"
            f"Odds: {odds:.2f} (Implied: {implied:.1f}%)\n"
            f"Our Prob: {our_prob:.1f}%\n"
            f"Edge: +{edge_pct:.1f}%\n\n"
            f"Signals:\n{signals_text}"
            f"{nav}\n\n"
            f"STAKE {stake_level}"
        )
        return msg


    async def send_alert(self, opportunity: Dict) -> Optional[str]:
        opp_id = opportunity["id"]
        match = opportunity["match"]
        market_key = opportunity.get("market_key") or opportunity.get("market")
        # Extract engine outputs (passed from main.py)
        edge_result  = opportunity.get("edge_result") or {}
        signal_eval  = opportunity.get("signal_eval") or {}
        # Core metrics
        odds = edge_result.get("decimal_odds", 0)
        edge = edge_result.get("edge_pct", 0)
        # Stake recommendation (still based on edge magnitude)
        stake = _recommended_stake(edge)
        # Navigation overlay (1win)
        league = match.get("league", "")
        nav_path  = LEAGUE_PATHS.get(league, "Football → search match")
        market   = get_market(market_key)
        market_name = market.name if market else market_key.replace("_", " ").title()
        tab_name  = MARKET_TABS.get(market_key, market_name)
        market_instruction = (
            f"\nFIND ON 1WIN:\n{nav_path}\n"
            f"Search: {match['home_team']} vs {match['away_team']}\n"
            f"Tab: {tab_name}"
        )
        # Build alert text with multi-signal data
        text = self._format_signal_alert(
            fixture=match,
            market_key=market_key,
            odds=odds,
            edge_result=edge_result,
            signal_eval=signal_eval,
            market_instruction=market_instruction,
        )
        # Button row
        keyboard = [
            [
                InlineKeyboardButton(f"    PLACED ₦{stake:,}", callback_data=f"placed|{stake}|{opp_id}"),
                InlineKeyboardButton("    SKIP", callback_data=f"skip|0|{opp_id}"),
            ]
        ]
        try:
            msg = await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="MarkdownV2",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            self.pending[opp_id] = {
                "opportunity": opportunity,
                "message_id":  msg.message_id,
                "timestamp":   datetime.utcnow().isoformat(),
                "stake":       stake,
            }
            logger.info(f"Alert sent: {opp_id} | edge={edge:.1f}%")
            return opp_id
        except Exception as e:
            logger.error(f"Alert send failed: {e}")
            return None




    async def _on_button(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        await query.answer()

        parts = query.data.split("|")
        action = parts[0]
        stake = float(parts[1])
        opp_id = parts[2]

        pending = self.pending.get(opp_id)
        if not pending:
            await query.edit_message_text(
                "   Opportunity expired or already handled."
            )
            return

        opp = pending["opportunity"]

        if action == "placed":
            # Log to DB for P&L tracking
            try:
                await self.db.log_bet(
                    opportunity_id=opp_id,
                    stake=stake,
                    odds=opp["bookmaker_odds"],
                )
                logger.info(f"Bet logged: {opp_id} ₦{stake}")
            except Exception as e:
                logger.error(f"DB log error: {e}")

            await query.edit_message_text(
                f"   *BET LOGGED*\n\n"
                f"₦{stake:,.0f} on "
                f"{_esc(opp['match']['home_team'])} vs "
                f"{_esc(opp['match']['away_team'])}\n"
                f"Market: {_esc(opp['market'])}\n"
                f"Odds: {opp['bookmaker_odds']}\n\n"
                f"_Good luck\\! Update result with /result_",
                parse_mode="MarkdownV2",
            )
            del self.pending[opp_id]

        elif action == "skip":
            await query.edit_message_text("        Skipped.")
            del self.pending[opp_id]


    async def _cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        await update.message.reply_text(
            "      *10x Betting Oracle* — Manual Mode\n\n"
            "Edge alerts arrive automatically\\.\n"
            "Place bets on 1win\\.ng then tap         PLACED\\.\n\n"
            "Commands:\n"
            "/stats \\— P\\&L summary\n"
            "/pending \\— open alerts",
            parse_mode="MarkdownV2",
        )


    async def _cmd_stats(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        stats = await self.db.get_stats()
        total = stats.get("total_bets", 0)
        wins = stats.get("wins", 0)
        pnl = stats.get("total_pnl") or 0.0
        wr = f"{(wins/total*100):.1f}%" if total else "N/A"

        await update.message.reply_text(
            f"      *10x Betting Stats*\n\n"
            f"Bets logged: {total}\n"
            f"Wins: {wins}\n"
            f"Win rate: {_esc(wr)}\n"
            f"P\\&L: ₦{pnl:,.0f}",
            parse_mode="MarkdownV2",
        )


    async def _cmd_pending(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if not self.pending:
            await update.message.reply_text("No pending alerts.")
            return
        lines = []
        for opp_id, data in self.pending.items():
            opp = data["opportunity"]
            lines.append(
                f"• {opp['match']['home_team']} vs "
                f"{opp['match']['away_team']} | "
                f"{opp['market']} | "
                f"+{opp['edge_percentage']}%"
            )
        await update.message.reply_text(
            "     *Pending:*\n\n" + "\n".join(lines),
            parse_mode="MarkdownV2",
        )


    async def shutdown(self):
        if self.app:
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram bot stopped")
