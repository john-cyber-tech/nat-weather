"""
National Weather Reader
=======================
A Flask web application that fetches plain-English weather reports from the
National Weather Service (NWS) public API for any US location.

Users enter a ZIP code or latitude/longitude pair and receive:
  - Current conditions (temperature, humidity, wind, pressure, visibility)
  - A 7-day / 14-period forecast
  - Any active NWS weather alerts for the area

External services used (all free, no API key required):
  - NWS API           https://api.weather.gov
  - OSM Nominatim     https://nominatim.openstreetmap.org  (ZIP → coordinates)
"""

from flask import Flask, render_template, request
import requests
from datetime import datetime, timezone

app = Flask(__name__)

# NWS requires a descriptive User-Agent; requests without one may be blocked.
NWS_HEADERS = {
    "User-Agent": "NationalWeatherReader/1.0 (educational project)",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Location helpers
# ---------------------------------------------------------------------------

def zip_to_latlon(zipcode):
    """Resolve a US ZIP code to geographic coordinates.

    Uses the OpenStreetMap Nominatim geocoding API, which is free and requires
    no API key. Returns a tuple of (latitude, longitude, display_name).
    All three values are None if the ZIP code cannot be found.

    Args:
        zipcode (str): A 5-digit US ZIP code.

    Returns:
        tuple: (float lat, float lon, str display_name) or (None, None, None).
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "postalcode": zipcode,
        "country": "US",
        "format": "json",
        "limit": 1,
    }
    # Nominatim requires a descriptive User-Agent per their usage policy.
    headers = {"User-Agent": "NationalWeatherReader/1.0 (educational project)"}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None, None, None
    r = results[0]
    lat = float(r["lat"])
    lon = float(r["lon"])
    display = r.get("display_name", f"ZIP {zipcode}")
    return lat, lon, display


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def c_to_f(c):
    """Convert Celsius to Fahrenheit, rounded to the nearest integer.

    Returns None if the input is None (NWS observation fields can be null
    when a sensor reading is unavailable).
    """
    if c is None:
        return None
    return round(c * 9 / 5 + 32)


def ms_to_mph(ms):
    """Convert meters-per-second to miles-per-hour, rounded to the nearest integer."""
    if ms is None:
        return None
    return round(ms * 2.237)


def pa_to_inhg(pa):
    """Convert Pascals to inches of mercury, rounded to two decimal places."""
    if pa is None:
        return None
    return round(pa * 0.0002953, 2)


def m_to_miles(m):
    """Convert meters to miles, rounded to one decimal place."""
    if m is None:
        return None
    return round(m / 1609.34, 1)


def degrees_to_compass(deg):
    """Convert a wind bearing in degrees to a 16-point compass direction (e.g. 'NNE').

    Returns None if deg is None.
    """
    if deg is None:
        return None
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[round(deg / 22.5) % 16]


# ---------------------------------------------------------------------------
# NWS response helpers
# ---------------------------------------------------------------------------

def val(obs_field):
    """Extract the numeric value from an NWS observation field dict.

    NWS observation fields are structured as {"value": <number>, "unitCode": "..."},
    but the value key can be absent or None when a sensor reading is unavailable.

    Args:
        obs_field: A dict with a "value" key, or any other type.

    Returns:
        The value if present, otherwise None.
    """
    if isinstance(obs_field, dict):
        return obs_field.get("value")
    return None


def condition_emoji(text):
    """Map a plain-text weather description to a representative emoji.

    Checks for keywords in priority order (most severe first) so that
    e.g. "Thunderstorms" does not accidentally match "rain" before "thunder".

    Args:
        text (str): A short weather description such as "Partly Cloudy".

    Returns:
        str: A single emoji character.
    """
    if not text:
        return "🌡️"
    t = text.lower()
    if "thunder" in t:
        return "⛈️"
    if "snow" in t or "blizzard" in t:
        return "❄️"
    if "rain" in t or "shower" in t or "drizzle" in t:
        return "🌧️"
    if "fog" in t or "mist" in t or "haze" in t:
        return "🌫️"
    if "cloudy" in t and "partly" in t:
        return "⛅"
    if "cloudy" in t or "overcast" in t:
        return "☁️"
    if "sunny" in t or "clear" in t:
        return "☀️"
    if "wind" in t:
        return "💨"
    return "🌤️"


# ---------------------------------------------------------------------------
# NWS data fetching
# ---------------------------------------------------------------------------

def fetch_weather(lat, lon):
    """Fetch all weather data for a coordinate pair from the NWS API.

    Makes up to four sequential API calls:
      1. /points/{lat},{lon}         — grid metadata and endpoint URLs
      2. /gridpoints/.../forecast    — 7-day forecast (up to 14 periods)
      3. /gridpoints/.../stations    — nearest observation station
         /stations/{id}/observations/latest — current conditions
      4. /alerts/active?point=...   — any active weather alerts

    Args:
        lat (float): Latitude in decimal degrees.
        lon (float): Longitude in decimal degrees.

    Returns:
        dict: Contains keys: city, state, station, current, periods, alerts.

    Raises:
        ValueError: If the coordinates fall outside NWS coverage (non-US).
        requests.exceptions.RequestException: On any network failure.
    """

    # Step 1 — Resolve coordinates to an NWS grid and fetch related URLs.
    points_resp = requests.get(
        f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}",
        headers=NWS_HEADERS,
        timeout=10,
    )
    if points_resp.status_code == 404:
        raise ValueError(
            "The National Weather Service does not cover that location. "
            "Make sure you entered a US location."
        )
    points_resp.raise_for_status()
    props = points_resp.json()["properties"]

    city = props.get("relativeLocation", {}).get("properties", {}).get("city", "")
    state = props.get("relativeLocation", {}).get("properties", {}).get("state", "")
    forecast_url = props["forecast"]
    stations_url = props["observationStations"]

    # Step 2 — Fetch the 7-day forecast (returned as up to 14 day/night periods).
    fc_resp = requests.get(forecast_url, headers=NWS_HEADERS, timeout=10)
    fc_resp.raise_for_status()
    raw_periods = fc_resp.json()["properties"]["periods"]

    periods = []
    for p in raw_periods[:14]:
        periods.append({
            "name": p["name"],
            "temp": p["temperature"],
            "temp_unit": p["temperatureUnit"],
            "wind_speed": p.get("windSpeed", ""),
            "wind_dir": p.get("windDirection", ""),
            "short": p.get("shortForecast", ""),
            "detail": p.get("detailedForecast", ""),
            "is_day": p.get("isDaytime", True),
            "emoji": condition_emoji(p.get("shortForecast", "")),
            "precip": p.get("probabilityOfPrecipitation", {}).get("value"),
        })

    # Step 3 — Fetch the latest observation from the nearest reporting station.
    # The stations endpoint returns a ranked list; we always use the first entry.
    current = None
    station_name = None
    st_resp = requests.get(stations_url, headers=NWS_HEADERS, timeout=10)
    if st_resp.ok and st_resp.json().get("features"):
        feat = st_resp.json()["features"][0]
        station_id = feat["properties"]["stationIdentifier"]
        station_name = feat["properties"]["name"]
        obs_resp = requests.get(
            f"https://api.weather.gov/stations/{station_id}/observations/latest",
            headers=NWS_HEADERS,
            timeout=10,
        )
        if obs_resp.ok:
            o = obs_resp.json()["properties"]
            temp_c = val(o.get("temperature"))
            # Heat index is used in warm conditions; wind chill in cold conditions.
            # NWS only populates the relevant one; fall back to the other if needed.
            feels_c = val(o.get("heatIndex")) or val(o.get("windChill"))
            current = {
                "description": o.get("textDescription", ""),
                "emoji": condition_emoji(o.get("textDescription", "")),
                "temp_f": c_to_f(temp_c),
                "temp_c": round(temp_c) if temp_c is not None else None,
                "feels_f": c_to_f(feels_c),
                "dewpoint_f": c_to_f(val(o.get("dewpoint"))),
                "humidity": (lambda h: round(h) if h is not None else None)(val(o.get("relativeHumidity"))),
                "wind_mph": ms_to_mph(val(o.get("windSpeed"))),
                "wind_dir": degrees_to_compass(val(o.get("windDirection"))),
                "wind_gust_mph": ms_to_mph(val(o.get("windGust"))),
                "barometer": pa_to_inhg(val(o.get("barometricPressure"))),
                "visibility_mi": m_to_miles(val(o.get("visibility"))),
                "timestamp": o.get("timestamp", ""),
            }

    # Step 4 — Fetch any active weather alerts for this point.
    alerts = []
    al_resp = requests.get(
        f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}",
        headers=NWS_HEADERS,
        timeout=10,
    )
    if al_resp.ok:
        for feat in al_resp.json().get("features", []):
            p = feat["properties"]
            alerts.append({
                "event": p.get("event", ""),
                "headline": p.get("headline", ""),
                "severity": p.get("severity", "Unknown"),
            })

    return {
        "city": city,
        "state": state,
        "station": station_name,
        "current": current,
        "periods": periods,
        "alerts": alerts,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    """Render the search form."""
    return render_template("index.html")


@app.route("/weather", methods=["POST"])
def weather():
    """Handle the search form submission and render the weather report.

    Accepts either a ZIP code or a raw latitude/longitude pair from the form.
    ZIP codes are resolved to coordinates before the NWS API is called.
    """
    zipcode = request.form.get("zipcode", "").strip()
    lat_raw = request.form.get("lat", "").strip()
    lon_raw = request.form.get("lon", "").strip()

    location_label = None

    try:
        if zipcode:
            lat, lon, location_label = zip_to_latlon(zipcode)
            if lat is None:
                return render_template(
                    "index.html",
                    error=f"Could not find a location for ZIP code '{zipcode}'. "
                          "Please check the code and try again.",
                )
        elif lat_raw and lon_raw:
            lat = float(lat_raw)
            lon = float(lon_raw)
        else:
            return render_template(
                "index.html",
                error="Please enter a ZIP code or a latitude and longitude.",
            )

        data = fetch_weather(lat, lon)

        # Fall back to the NWS-provided city/state if Nominatim did not supply a label.
        if not location_label:
            parts = [data["city"], data["state"]]
            location_label = ", ".join(p for p in parts if p) or f"{lat:.4f}, {lon:.4f}"

        fetched_at = datetime.now(timezone.utc).astimezone().strftime("%B %d, %Y at %I:%M %p %Z")

        return render_template(
            "weather.html",
            location=location_label,
            lat=lat,
            lon=lon,
            fetched_at=fetched_at,
            **data,
        )

    except ValueError as e:
        return render_template("index.html", error=str(e))
    except requests.exceptions.RequestException as e:
        return render_template(
            "index.html",
            error=f"Network error while contacting the National Weather Service: {e}",
        )


if __name__ == "__main__":
    app.run(debug=True)
