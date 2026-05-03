# Methodology: Weather Data via OpenWeatherMap

**Source:** [OpenWeatherMap Current Weather API](https://openweathermap.org/current)
**Tier:** Free (60 calls/min, 1M calls/month)
**Cost:** $0
**Auth:** API key (free registration)
**Last Updated:** 2026-05-03

---

## Why OpenWeatherMap

- **Free tier generous** — 60 calls/min, more than enough for match-day weather
- **Returns rain (1h), wind speed, temperature, humidity** — all key factors for betting edge
- **Stadium coordinates** — we map venue names to lat/lon via a pre-cached `venue_coordinates.json`
- **No proxy required** — REST API, no blocks or geo-restrictions from Nigeria

---

## Implementation

### Data Flow

```
Match fixture (venue name)
  └─ venue_coordinates.json lookup → lat, lon
       └─ GET https://api.openweathermap.org/data/2.5/weather?lat=...&lon=...&appid=...&units=metric
            └─ Returns: temp, rain_1h, wind_speed, humidity
```

### Code Location

`src/collectors/weather.py` — `WeatherCollector` class

### API Call

```python
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
params = {
    "lat":   latitude,
    "lon":   longitude,
    "appid": API_KEY,
    "units": "metric",
}
```

### Response Shape

```json
{
  "main": { "temp": 15.18, "humidity": 75 },
  "wind": { "speed": 1.31 },
  "rain": { "1h": 0.0 }
}
```

### Extracted Fields

| Field | Key | Default If Missing |
|-------|-----|-------------------|
| Temperature | `main.temp` | 20°C |
| Rain (1h) | `rain.1h` | 0 mm |
| Wind speed | `wind.speed` | 0 m/s |
| Humidity | `main.humidity` | 50% |

---

## Integration Points

**Signal engine** (`src/models/edge.py`) consumes weather data in `_add_weather_bias()`:
- Heavy rain → favours defensive/set-piece teams
- Strong wind → reduces passing accuracy
- Extreme temperature → favours acclimated squad

**Entry point:** `WeatherCollector.get_for_match(match)` — takes a Match object with `latitude` and `longitude` attributes.

---

## Setup

1. Register at [openweathermap.org](https://openweathermap.org) (free)
2. Get API key from dashboard
3. Add to `.env`:

```
OPENWEATHERMAP_API_KEY=your_key_here
```

4. Install dependency:

```bash
pip install aiohttp
```

---

## Failure Modes

| Scenario | Behaviour |
|----------|-----------|
| No API key | Returns `None` silently |
| Invalid coords | Returns weather for 0,0 (Atlantic Ocean) |
| HTTP 401 | Returns `None` + warning log |
| HTTP 429 (rate limit) | Returns `None` + warning log |
| Network timeout | Returns `None` + error log |

**All failures are graceful** — signal engine treats `None` as neutral weather (no bias applied).

---

## Limitations

- Free tier only provides **current weather**, not forecasts
- Stadium coordinates must be pre-cached (no geocoding in this implementation)
- Rain data only includes `1h` precipitation — no 3h or daily aggregates
- No historical weather data available on free tier
