import logging

logger = logging.getLogger("10xbet.edge")

# Base probability adjustments per market type based on signals
# Each key maps to a dict of {signal_condition: adjustment}
MARKET_SIGNAL_WEIGHTS = {
    # Total goals markets — boosted by attacking form, weather
    "total_over_25": {
        "heavy_rain":       -0.08,
        "high_wind":        -0.05,
        "hot_form_home":    +0.10,
        "hot_form_away":    +0.08,
        "high_scoring":     +0.12,
        "derby":            +0.06,
        "must_win":         +0.08,
    },
    "total_over_35": {
        "heavy_rain":       -0.10,
        "high_wind":        -0.06,
        "hot_form_home":    +0.12,
        "hot_form_away":    +0.10,
        "high_scoring":     +0.15,
        "derby":            +0.07,
        "must_win":         +0.09,
    },
    "total_under_25": {
        "heavy_rain":       +0.10,
        "high_wind":        +0.08,
        "poor_form_both":   +0.12,
        "nothing_to_lose": +0.06,
    },
    "btts_yes": {
        "heavy_rain":       -0.06,
        "hot_form_home":    +0.08,
        "hot_form_away":    +0.08,
        "h2h_both_score":   +0.10,
        "must_win":         +0.05,
    },
    "btts_no": {
        "heavy_rain":        +0.08,
        "poor_form_away":    +0.10,
        "nothing_to_lose": +0.06,
    },
    "corners_over": {
        "high_wind":         +0.12,
        "hot_form_home":     +0.06,
        "must_win":          +0.08,
        "derby":             +0.10,
        "attacking_style": +0.08,
    },
    "1h_total_over": {
        "must_win":          +0.10,
        "derby":             +0.08,
        "hot_form_home":     +0.06,
        "high_scoring":      +0.08,
    },
    "draw_and_over": {
        "heavy_rain":        -0.05,
        "nothing_to_lose": +0.08,
        "h2h_draws":         +0.10,
    },
    "win_either_half": {
        "hot_form_home":     +0.10,
        "must_win":          +0.08,
        "derby":             +0.06,
    },
    "to_win_to_nil": {
        "heavy_rain":        +0.06,
        "poor_form_away":    +0.12,
        "hot_form_home":     +0.08,
    },
    "double_chance_home": {
        "hot_form_home":     +0.10,
        "must_win":          +0.08,
        "relegation":        +0.10,
    },
    "double_chance_away": {
        "hot_form_away":     +0.10,
        "title_race":        +0.08,
    },
    "halftime_fulltime": {
        "must_win":          +0.06,
        "derby":             +0.05,
    },
}

# Default weights for markets not explicitly listed
DEFAULT_WEIGHTS = {
    "heavy_rain":              -0.05,
    "high_wind":               -0.03,
    "hot_form_home": +0.07,
    "hot_form_away": +0.06,
    "must_win":                +0.06,
    "derby":                   +0.05,
}

class EdgeCalculator:
    """
    Calculates edge for each market using signal engine output.
    Edge = Our probability - Implied probability (from odds).
    """

    def __init__(self, config=None):
        self.threshold = 0.12
        if config:
            try:
                self.threshold = float(
                    config.get("edge", {}).get("threshold", 0.12)
                )
            except Exception:
                pass
        logger.info(
            "EdgeCalculator ready — threshold=%.0f%%",
            self.threshold * 100
        )

    def calculate(self, market_key, decimal_odds, signal_eval,
                          weather=None, team_form=None, h2h=None):
        """
        Calculate edge for a specific market.

        market_key           — internal market key e.g. "total_over_25"
        decimal_odds — SportyBet decimal odds e.g. 1.87
        signal_eval          — output from SignalEngine.evaluate()
        weather              — raw weather dict
        team_form            — raw team form dict
        h2h                  — raw h2h dict

        Returns dict with edge, our_prob, implied_prob, signal_summary
        """
        if not decimal_odds or decimal_odds <= 1.0:
            return None

        # Implied probability from bookmaker odds
        implied_prob = 1.0 / decimal_odds

        # Build signal condition flags
        conditions = self._build_conditions(
            signal_eval, weather, team_form, h2h
        )

        # Get weights for this market
        weights = MARKET_SIGNAL_WEIGHTS.get(market_key, DEFAULT_WEIGHTS)

        # Calculate adjustment
        adjustment = 0.0
        applied = []
        for condition, adj in weights.items():
            if conditions.get(condition, False):
                adjustment += adj
                direction = "+" if adj > 0 else ""
                applied.append(f"{condition}({direction}{adj:.0%})")

        # Our probability = implied + adjustments
        our_prob = max(0.01, min(0.99, implied_prob + adjustment))

        # Edge
        edge = our_prob - implied_prob

        result = {
            "market_key":    market_key,
            "decimal_odds": decimal_odds,
            "implied_prob": round(implied_prob, 4),
            "our_prob":      round(our_prob, 4),
            "edge":          round(edge, 4),
            "edge_pct":      round(edge * 100, 2),
            "has_edge":      edge >= self.threshold,
            "conditions":    applied,
        }

        if result["has_edge"]:
            logger.info(
                "EDGE: %s | odds=%.2f implied=%.1f%% ours=%.1f%% edge=+%.1f%%",
                market_key, decimal_odds,
                implied_prob * 100, our_prob * 100, edge * 100
            )

        return result

    def calculate_all(self, odds_dict, signal_eval,
                      weather=None, team_form=None, h2h=None):
        """
        Calculate edge for all available markets.
        Returns list of markets with edge >= threshold.
        """
        opportunities = []
        for market_key, decimal_odds in odds_dict.items():
            # Skip non-numeric entries (e.g., meta)
            if not isinstance(decimal_odds, (int, float)):
                continue
            result = self.calculate(
                market_key, decimal_odds, signal_eval,
                weather, team_form, h2h
            )
            if result and result["has_edge"]:
                opportunities.append(result)
        return opportunities

    def _build_conditions(self, signal_eval, weather, team_form, h2h):
        conditions = {}

        # Weather flags
        if weather:
            rain = weather.get("rain_mm", 0) or 0
            wind = weather.get("wind_speed", 0) or 0
            conditions["heavy_rain"] = rain >= 5.0
            conditions["high_wind"]  = wind >= 20.0

        # Team form flags
        if team_form:
            home = team_form.get("home", {})
            away = team_form.get("away", {})
            home_wins = home.get("last_5", []).count("W")
            away_wins = away.get("last_5", []).count("W")
            conditions["hot_form_home"] = home_wins >= 3
            conditions["hot_form_away"] = away_wins >= 3
            conditions["high_scoring"]  = (home.get("goals_scored_avg", 0) or 0) >= 2.5
            conditions["poor_form_away"] = away_wins <= 1

        # H2H flags
        if h2h:
            total = h2h.get("home_wins", 0) + h2h.get("away_wins", 0) + h2h.get("draws", 0)
            conditions["h2h_both_score"] = total >= 3
            conditions["h2h_draws"]      = h2h.get("draws", 0) >= 2

        # Motivation flags (from signal_eval groups)
        for group in signal_eval.get("groups", []):
            if group.name == "Motivation" and group.active:
                reasons_str = " ".join(group.reason).lower()
                conditions["derby"]             = "derby" in reasons_str
                conditions["title_race"]        = "title race" in reasons_str
                conditions["relegation"]        = "relegation" in reasons_str
                conditions["must_win"]          = "must win" in reasons_str
                conditions["nothing_to_lose"]   = "nothing to lose" in reasons_str

        return conditions
