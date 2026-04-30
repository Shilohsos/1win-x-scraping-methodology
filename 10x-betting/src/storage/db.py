"""10x Betting — Database Layer
SQLite via aiosqlite. WAL mode for concurrent reads.
Tables: matches, opportunities, bets
"""
import aiosqlite
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger("10xbet.db")
DB_PATH = Path("data/10xbet.db")

async def get_db() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db

async def init_db():
    """Idempotent — safe to call on every startup."""
    db = await get_db()
    try:
        # matches table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id           TEXT PRIMARY KEY,
                home_team    TEXT NOT NULL,
                away_team    TEXT NOT NULL,
                league       TEXT NOT NULL,
                kickoff      TEXT,
                venue        TEXT,
                referee_id   TEXT,
                latitude     REAL,
                longitude    REAL,
                created_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        # opportunities table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                id             TEXT PRIMARY KEY,
                match_id       TEXT NOT NULL,
                market         TEXT NOT NULL,
                bookmaker_odds REAL,
                implied_prob   REAL,
                hermes_prob    REAL,
                edge_pct       REAL,
                weather_json   TEXT DEFAULT '{}',
                referee_json   TEXT DEFAULT '{}',
                status         TEXT DEFAULT 'pending',
                created_at     TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (match_id) REFERENCES matches(id)
            )
        """)
        # bets table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                id             TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                stake          REAL NOT NULL,
                bookmaker_odds REAL,
                status         TEXT DEFAULT 'placed',
                result         TEXT,
                pnl            REAL,
                placed_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
            )
        """)
        # referee_stats table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referee_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referee_name TEXT UNIQUE,
                avg_yellow_cards REAL DEFAULT 0,
                avg_red_cards REAL DEFAULT 0,
                avg_fouls REAL DEFAULT 0,
                strictness_score REAL DEFAULT 0,
                matches_scraped INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        # team_form table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS team_form (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT,
                league TEXT,
                last_5 TEXT,
                goals_scored_avg REAL,
                goals_conceded_avg REAL,
                wins INTEGER,
                draws INTEGER,
                losses INTEGER,
                position INTEGER,
                points INTEGER,
                updated_at TEXT
            )
        """)
        # head_to_head table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS head_to_head (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                home_team TEXT,
                away_team TEXT,
                h2h_summary TEXT,
                home_wins INTEGER,
                away_wins INTEGER,
                draws INTEGER,
                avg_goals REAL,
                updated_at TEXT
            )
        """)
        # player_form table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS player_form (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT,
                team_name TEXT,
                rating REAL,
                goals_last_5 INTEGER,
                assists_last_5 INTEGER,
                injury_status TEXT DEFAULT 'fit',
                injury_return TEXT,
                motivation_flag TEXT,
                updated_at TEXT
            )
        """)
        # sentiment_data table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT,
                match_key TEXT,
                source TEXT,
                sentiment_score REAL,
                headline_summary TEXT,
                scraped_at TEXT
            )
        """)
        # motivation_data table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS motivation_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT,
                match_key TEXT,
                is_derby INTEGER DEFAULT 0,
                title_race INTEGER DEFAULT 0,
                relegation_battle INTEGER DEFAULT 0,
                must_win INTEGER DEFAULT 0,
                nothing_to_lose INTEGER DEFAULT 0,
                trophy_match INTEGER DEFAULT 0,
                motivation_score REAL DEFAULT 0,
                updated_at TEXT
            )
        """)
        await db.commit()
    finally:
        await db.close()
    logger.info("✓ Database initialized")

class Database:
    async def initialize(self):
        await init_db()

    # ── Matches ──────────────────────────────────────────────
    async def upsert_match(self, match) -> str:
        db = await get_db()
        try:
                await db.execute("""
                    INSERT OR REPLACE INTO matches
                    (id, home_team, away_team, league, kickoff, venue,
                     referee_id, latitude, longitude)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(match.id),
                    match.home_team,
                    match.away_team,
                    match.league,
                    match.kickoff.isoformat() if match.kickoff else None,
                    match.venue,
                    match.referee_id,
                    match.latitude,
                    match.longitude,
                ))
                await db.commit()
        finally:
            await db.close()
        return str(match.id)

    # ── Opportunities ─────────────────────────────────────────
    async def log_opportunity(self, opp: Dict) -> str:
        opp_id = opp["id"]
        match  = opp["match"]
        db = await get_db()
        try:
                await db.execute("""
                    INSERT OR REPLACE INTO opportunities
                    (id, match_id, market, bookmaker_odds, implied_prob,
                     hermes_prob, edge_pct, weather_json, referee_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    opp_id,
                    str(match["id"]),
                    opp["market"],
                    opp["bookmaker_odds"],
                    opp["implied_probability"],
                    opp["hermes_probability"],
                    opp["edge_percentage"],
                    json.dumps(opp.get("weather") or {}),
                    json.dumps(opp.get("referee_stats") or {}),
                ))
                await db.commit()
        finally:
            await db.close()
        return opp_id

    async def get_opportunity(self, opp_id: str) -> Optional[Dict]:
        db = await get_db()
        try:
                async with db.execute(
                    "SELECT * FROM opportunities WHERE id = ?", (opp_id,)
                ) as cur:
                    row = await cur.fetchone()
                    if not row:
                        return None
                    d = dict(row)
                    d["weather"]       = json.loads(d.pop("weather_json", "{}"))
                    d["referee_stats"] = json.loads(d.pop("referee_json", "{}"))
                    return d

        finally:
            await db.close()
    async def mark_opportunity(self, opp_id: str, status: str):
        db = await get_db()
        try:
                await db.execute(
                    "UPDATE opportunities SET status=? WHERE id=?",
                    (status, opp_id)
                )
                await db.commit()

        finally:
            await db.close()
    # ── Bets ──────────────────────────────────────────────────
    async def log_bet(self, opportunity_id: str, stake: float, odds: float) -> str:
        bet_id = f"bet_{opportunity_id}_{int(datetime.utcnow().timestamp())}"
        db = await get_db()
        try:
                await db.execute("""
                    INSERT INTO bets (id, opportunity_id, stake, bookmaker_odds)
                    VALUES (?, ?, ?, ?)
                """, (bet_id, opportunity_id, stake, odds))
                await db.commit()
        finally:
            await db.close()
        return bet_id

    async def update_bet_result(self, bet_id: str, result: str, pnl: float):
        db = await get_db()
        try:
                await db.execute(
                    "UPDATE bets SET result=?, pnl=?, status='settled' WHERE id=?",
                    (result, pnl, bet_id)
                )
                await db.commit()

        finally:
            await db.close()
    # ── Stats ─────────────────────────────────────────────────
    async def get_stats(self) -> Dict:
        db = await get_db()
        try:
                async with db.execute("""
                    SELECT
                        COUNT(*)                                         AS total_bets,
                        SUM(CASE WHEN result='win'  THEN 1 ELSE 0 END)  AS wins,
                        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END)  AS losses,
                        ROUND(SUM(pnl), 2)                              AS total_pnl,
                        ROUND(AVG(stake), 2)                            AS avg_stake
                    FROM bets
                    WHERE status = 'settled'
                """) as cur:
                    row = await cur.fetchone()
                    return dict(row) if row else {
                        "total_bets": 0, "wins": 0,
                        "losses": 0, "total_pnl": 0.0, "avg_stake": 0.0
                    }

        finally:
            await db.close()
    async def get_pending_opportunities(self) -> list:
        db = await get_db()
        try:
                async with db.execute(
                    "SELECT * FROM opportunities WHERE status = 'pending' "
                    "ORDER BY created_at DESC LIMIT 50"
                ) as cur:
                    rows = await cur.fetchall()
                    return [dict(r) for r in rows]
        finally:
            await db.close()
