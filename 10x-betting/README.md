# 1win x Scraping Methodology

**Project:** 10x Betting — Automated EPL edge detection system
**Stack:** Python + CloakBrowser + ScraperFC + OpenWeatherMap
**Repository:** github.com/Shilohsos/1win-x-scraping-methodology

---

## Data Sources

| Collector | Source | Auth | Status |
|-----------|--------|------|--------|
| Fixtures | LiveScore (public API) | None | ✅ |
| Form/H2H | Sofascore (API) | CloakBrowser proxy | ✅ |
| Lineups | Sofascore (API) | CloakBrowser proxy | ✅ |
| Injuries | Sofascore (player profile API) | CloakBrowser proxy | ✅ |
| Odds | 1win.ng (CloakBrowser) | Login + SA proxy | ✅ |
| Weather | OpenWeatherMap (REST) | API key | ✅ |

---

## Methodology Documents

- [OpenWeatherMap Weather](docs/METHODOLOGY_OPENWEATHERMAP.md) — Current weather data for match venues
- *(More to come: Sofascore injuries, LiveScore fixtures, 1win odds)*

---

## Quick Start

```bash
git clone https://github.com/Shilohsos/1win-x-scraping-methodology.git
cd 1win-x-scraping-methodology
cp .env.example .env   # fill in your keys
pip install -r requirements.txt
python src/main.py
```

**Last Updated:** 2026-05-03
