import logging
from src.models.motivation import MotivationScorer

logger = logging.getLogger("10xbet.signal_engine")

MIN_GROUPS_FOR_ALERT = 2       # minimum signal groups needed to fire alert
HIGH_CONFIDENCE_THRESHOLD = 3       # groups needed for STAKE HIGH

class SignalGroup:
    """Represents one evaluated signal group."""

    def __init__(self, name, active, score, reason):
        self.name = name
        self.active = active         # True = this group contributes a signal
        self.score = score           # 0.0 - 1.0
        self.reason = reason         # human-readable explanation

    def __repr__(self):
        status = "ACTIVE" if self.active else "inactive"
        return f"[{status}] {self.name}: {self.reason} (score={self.score:.2f})"

class SignalEngine:
    """
    Evaluates all signal groups for a fixture and determines
    whether to fire an alert, and at what confidence level.
    """

    def __init__(self):
        self.motivation_scorer = MotivationScorer()
        logger.info("SignalEngine ready")

    def evaluate(self, fixture, odds, weather=None, referee=None,
                   team_form=None, h2h=None, injuries=None,
                   sentiment=None, player_form=None,
                   standings=None):
        """
        Evaluate all 6 signal groups for a fixture.
        Returns evaluation dict with alert decision.

        fixture      — Match object (home_team, away_team, competition)
        odds         — dict of {market_key: decimal_odds}
        weather      — dict from weather collector
        referee      — dict from referee/sofascore
        team_form — dict {home: {...}, away: {...}}
        h2h          — dict from flashscore
        injuries     — dict {home: [...], away: [...]}
        sentiment — dict {news: score, reddit: score, twitter: score}
        player_form — dict {home: [...], away: [...]}
        standings — dict {home: {position, points}, away: {position, points}}
        """
        home = fixture.home_team
        away = fixture.away_team
        groups = []

        # ── GROUP 1: MATCH ENVIRONMENT ──────────────────────────
        env_score, env_reason = self._eval_environment(weather, referee)
        groups.append(SignalGroup(
            "Match Environment",
            env_score >= 0.3,
            env_score,
            env_reason
        ))

        # ── GROUP 2: TEAM INTELLIGENCE ──────────────────────────
        intel_score, intel_reason = self._eval_team_intelligence(
            team_form, h2h
        )
        groups.append(SignalGroup(
            "Team Intelligence",
            intel_score >= 0.3,
            intel_score,
            intel_reason
        ))

        # ── GROUP 3: MOTIVATION ──────────────────────────────────
        mot_score, mot_reason = self._eval_motivation(
            home, away, standings
        )
        groups.append(SignalGroup(
            "Motivation",
            mot_score >= 0.25,
            mot_score,
            mot_reason
        ))

        # ── GROUP 4: AVAILABILITY ────────────────────────────────
        avail_score, avail_reason = self._eval_availability(injuries)
        groups.append(SignalGroup(
            "Availability",
            False,         # Availability is INFORMATIONAL ONLY — never blocks
            avail_score,
            avail_reason
        ))

        # ── GROUP 5: SENTIMENT ───────────────────────────────────
        sent_score, sent_reason = self._eval_sentiment(sentiment)
        groups.append(SignalGroup(
            "Sentiment",
            sent_score >= 0.2,
            sent_score,
            sent_reason
        ))

        # ── GROUP 6: PLAYER FORM ─────────────────────────────────
        form_score, form_reason = self._eval_player_form(player_form)
        groups.append(SignalGroup(
            "Player Form",
            form_score >= 0.3,
            form_score,
            form_reason
        ))

        # ── DECISION ─────────────────────────────────────────────
        active_groups = [g for g in groups if g.active]
        # Note: Availability is always excluded from count
        signal_count = len([g for g in active_groups
                            if g.name != "Availability"])

        should_alert = signal_count >= MIN_GROUPS_FOR_ALERT
        high_confidence = signal_count >= HIGH_CONFIDENCE_THRESHOLD
        stake_level = "HIGH       " if high_confidence else "LOW   "

        logger.info(
            "%s vs %s | %d groups active | alert=%s | stake=%s",
            home, away, signal_count, should_alert, stake_level
        )

        return {
            "should_alert":      should_alert,
            "high_confidence": high_confidence,
            "stake_level":       stake_level,
            "signal_count":        signal_count,
            "groups":              groups,
            "active_groups":       active_groups,
        }

    # ── PRIVATE EVALUATORS ───────────────────────────────────────

    def _eval_environment(self, weather, referee):
        score = 0.0
        reasons = []

        if weather:
            rain = weather.get("rain_mm", 0) or 0
            wind = weather.get("wind_speed", 0) or 0
            if rain >= 5.0:
                score += 0.4
                reasons.append(f"Heavy rain {rain}mm — affects play")
            elif rain >= 2.0:
                score += 0.2
                reasons.append(f"Light rain {rain}mm")

            if wind >= 20.0:
                score += 0.3
                reasons.append(f"High wind {wind}m/s — boosts corners")

        if referee:
            strictness = referee.get("strictness", 0) or 0
            avg_yellow = referee.get("avg_yellow", 0) or 0
            if strictness >= 5.0:
                score += 0.3
                reasons.append(
                    f"Strict referee — {avg_yellow:.1f} yellows/game"
                )
            elif strictness >= 3.0:
                score += 0.15
                reasons.append(f"Moderate referee — {avg_yellow:.1f} yellows/game")

        reason = " | ".join(reasons) if reasons else "Normal conditions"
        return min(score, 1.0), reason

    def _eval_team_intelligence(self, team_form, h2h):
        score = 0.0
        reasons = []

        if team_form:
            home_form = team_form.get("home", {})
            away_form = team_form.get("away", {})

            home_last5 = home_form.get("last_5", [])
            away_last5 = away_form.get("last_5", [])

            home_wins = home_last5.count("W") if home_last5 else 0
            away_wins = away_last5.count("W") if away_last5 else 0

            if home_wins >= 4:
                score += 0.35
                reasons.append(
                    f"Home in hot form — {home_wins}/5 wins"
                )
            elif home_wins >= 3:
                score += 0.20
                reasons.append(f"Home good form — {home_wins}/5 wins")

            if away_wins >= 4:
                score += 0.25
                reasons.append(f"Away in hot form — {away_wins}/5 wins")

            home_avg_goals = home_form.get("goals_scored_avg", 0) or 0
            if home_avg_goals >= 2.5:
                score += 0.20
                reasons.append(
                    f"High scoring home — {home_avg_goals:.1f} goals/game avg"
                )

        if h2h:
            total = (h2h.get("home_wins", 0)
                       + h2h.get("away_wins", 0)
                       + h2h.get("draws", 0))
            if total >= 3:
                score += 0.15
                reasons.append(
                    f"H2H data: {h2h.get('home_wins',0)}W-"
                    f"{h2h.get('draws',0)}D-{h2h.get('away_wins',0)}L"
                )

        reason = " | ".join(reasons) if reasons else "Insufficient form data"
        return min(score, 1.0), reason

    def _eval_motivation(self, home_team, away_team, standings):
        pos_home = None
        pos_away = None
        pts_home = None
        pts_away = None
        games_rem = 10

        if standings:
            h = standings.get("home", {})
            a = standings.get("away", {})
            pos_home = h.get("position")
            pos_away = a.get("position")
            pts_home = h.get("points")
            pts_away = a.get("points")
            games_rem = h.get("games_remaining", 10)

        mot = self.motivation_scorer.get_fixture_motivation(
            home_team, away_team,
            home_pos=pos_home, away_pos=pos_away,
            home_pts=pts_home, away_pts=pts_away,
            games_remaining=games_rem
        )

        score = mot["motivation_score"]
        reasons = mot["reasons"][:2] if mot["reasons"] else ["Standard fixture"]
        reason = " | ".join(reasons)
        return score, reason

    def _eval_availability(self, injuries):
        if not injuries:
            return 0.0, "No injury data"
        home_inj = injuries.get("home", [])
        away_inj = injuries.get("away", [])
        total = len(home_inj) + len(away_inj)
        names = [i.get("player", "") for i in (home_inj + away_inj)[:3]]
        if total == 0:
            return 0.0, "No injuries reported"
        reason = f"{total} injuries — {', '.join(names)}"
        # Score is just informational — high injuries = high impact score
        score = min(total * 0.1, 0.5)
        return score, reason

    def _eval_sentiment(self, sentiment):
        if not sentiment:
            return 0.0, "No sentiment data"
        scores = []
        sources = []
        for source, val in sentiment.items():
            if isinstance(val, dict):
                s = val.get("score", 0)
            else:
                s = val or 0
            if s != 0:
                scores.append(s)
                sources.append(f"{source}:{s:+.2f}")
        if not scores:
            return 0.0, "Neutral sentiment"
        avg = sum(scores) / len(scores)
        # Convert -1..1 sentiment to 0..1 signal score
        signal_score = abs(avg) * 0.8
        direction = "positive" if avg > 0 else "negative"
        reason = f"Sentiment {direction} ({', '.join(sources[:2])})"
        return min(signal_score, 1.0), reason

    def _eval_player_form(self, player_form):
        if not player_form:
            return 0.0, "No player form data"
        home_players = player_form.get("home", [])
        away_players = player_form.get("away", [])
        all_players = home_players + away_players
        if not all_players:
            return 0.0, "No player ratings available"
        good_form = [p for p in all_players
                     if p.get("form") == "good" or
                     (p.get("avg_rating", 0) or 0) >= 7.0]
        if not good_form:
            return 0.0, "No players in exceptional form"
        names = [p.get("player", "Unknown") for p in good_form[:2]]
        score = min(len(good_form) * 0.2, 0.8)
        reason = f"{len(good_form)} players in good form — {', '.join(names)}"
        return score, reason
