import logging

logger = logging.getLogger("10xbet.motivation")

# Known derby fixtures — add more as needed
DERBY_PAIRS = [
    # EPL
    ("Arsenal", "Tottenham"),
    ("Chelsea", "Arsenal"),
    ("Chelsea", "Tottenham"),
    ("Manchester City", "Manchester United"),
    ("Liverpool", "Everton"),
    ("Newcastle", "Sunderland"),
    ("Aston Villa", "Birmingham"),
    ("West Ham", "Millwall"),
    ("Crystal Palace", "Brighton"),
    ("Leeds United", "Manchester United"),
    # La Liga
    ("Real Madrid", "Barcelona"),
    ("Real Madrid", "Atletico Madrid"),
    ("Barcelona", "Espanyol"),
    ("Sevilla", "Betis"),
    ("Athletic Bilbao", "Real Sociedad"),
    ("Valencia", "Villarreal"),
]

class MotivationScorer:
    """
    Calculates motivation signals for each team in a fixture.
    Uses league standings data to detect title races,
    relegation battles, and must-win situations.
    """

    def __init__(self, db=None):
        self.db = db
        logger.info("MotivationScorer ready")

    def is_derby(self, home_team, away_team):
        """Check if the fixture is a known derby."""
        for pair in DERBY_PAIRS:
            a, b = pair
            if (a.lower() in home_team.lower() or home_team.lower() in a.lower()) and                (b.lower() in away_team.lower() or away_team.lower() in b.lower()):
                return True
            if (b.lower() in home_team.lower() or home_team.lower() in b.lower()) and                (a.lower() in away_team.lower() or away_team.lower() in a.lower()):
                return True
        return False

    def score_team(self, team_name, position, points,
                      total_teams, games_remaining, league):
        """
        Returns a motivation dict for a team based on
        their league position and points situation.
        """
        signals = {
            "title_race":          False,
            "top4_race":           False,
            "relegation_battle":   False,
            "must_win":            False,
            "nothing_to_lose":     False,
            "motivation_score":    0.0,
            "reason":              [],
        }

        if position is None or points is None:
            return signals

        games_remaining = max(games_remaining, 0)

        # Title race: top 3, close race
        if position <= 3 and games_remaining <= 10:
            signals["title_race"] = True
            signals["must_win"] = True
            signals["motivation_score"] += 0.35
            signals["reason"].append(
                f"Title race — P{position} with {games_remaining} games left"
            )

        # Top 4 race: positions 4-7 with few games left
        elif position <= 7 and games_remaining <= 8:
            signals["top4_race"] = True
            signals["motivation_score"] += 0.20
            signals["reason"].append(
                f"Top 4 push — P{position}"
            )

        # Relegation: bottom 5 teams or within 3 pts of drop zone
        relegation_zone = total_teams - 2       # bottom 3
        if position >= relegation_zone - 2:
            signals["relegation_battle"] = True
            signals["must_win"] = True
            signals["motivation_score"] += 0.40
            signals["reason"].append(
                f"Relegation battle — P{position}"
            )

        # Already relegated / safe → nothing to lose
        if position >= total_teams - 1 and games_remaining <= 4:
            signals["nothing_to_lose"] = True
            signals["motivation_score"] += 0.10
            signals["reason"].append("Nothing to lose — already relegated")

        if position == 1 and games_remaining <= 5:
            signals["motivation_score"] += 0.10
            signals["reason"].append("League leaders — protect position")

        signals["motivation_score"] = min(signals["motivation_score"], 1.0)
        return signals

    def get_fixture_motivation(self, home_team, away_team,
                                 home_pos=None, away_pos=None,
                                 home_pts=None, away_pts=None,
                                 total_teams=20, games_remaining=10,
                                 league="PL"):
        """
        Full motivation assessment for both teams in a fixture.
        Returns combined motivation data dict.
        """
        derby = self.is_derby(home_team, away_team)
        home_mot = self.score_team(
            home_team, home_pos, home_pts,
            total_teams, games_remaining, league
        )
        away_mot = self.score_team(
            away_team, away_pos, away_pts,
            total_teams, games_remaining, league
        )

        combined_score = max(
            home_mot["motivation_score"],
            away_mot["motivation_score"]
        )
        if derby:
            combined_score = min(combined_score + 0.30, 1.0)

        reasons = []
        if derby:
            reasons.append(f"DERBY MATCH — {home_team} vs {away_team}")
        reasons.extend(home_mot["reason"])
        reasons.extend(away_mot["reason"])

        result = {
            "is_derby":             derby,
            "title_race":           home_mot["title_race"] or away_mot["title_race"],
            "relegation_battle": home_mot["relegation_battle"] or
                                 away_mot["relegation_battle"],
            "must_win":             home_mot["must_win"] or away_mot["must_win"],
            "nothing_to_lose":      home_mot["nothing_to_lose"] or
                                    away_mot["nothing_to_lose"],
            "motivation_score":     round(combined_score, 2),
            "reasons":              reasons,
            "home":                 home_mot,
            "away":                 away_mot,
        }

        logger.info(
            "Motivation %s vs %s: score=%.2f derby=%s reasons=%s",
            home_team, away_team,
            result["motivation_score"],
            derby,
            reasons[:2]
        )
        return result
