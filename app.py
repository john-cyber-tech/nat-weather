from flask import Flask, render_template, request
import requests
from datetime import datetime, timezone

app = Flask(__name__)

NWS_HEADERS = {
    "User-Agent": "NationalWeatherReader/1.0 (educational project)",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def zip_to_latlon(zipcode):
    """Return (lat, lon, display_name) for a US ZIP code via OpenStreetMap Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "postalcode": zipcode,
        "country": "US",
        "format": "json",
        "limit": 1,
    }
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


def c_to_f(c):
    if c is None:
        return None
    return round(c * 9 / 5 + 32)


def ms_to_mph(ms):
    if ms is None:
        return None
    return round(ms * 2.237)


def pa_to_inhg(pa):
    if pa is None:
        return None
    return round(pa * 0.0002953, 2)


def m_to_miles(m):
    if m is None:
        return None
    return round(m / 1609.34, 1)


def degrees_to_compass(deg):
    if deg is None:
        return None
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[round(deg / 22.5) % 16]


def val(obs_field):
    """Safely extract .value from an NWS observation field dict."""
    if isinstance(obs_field, dict):
        return obs_field.get("value")
    return None


def condition_emoji(text):
    """Map a short weather description to an emoji."""
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
    """Return a dict of weather data for the given coordinates."""

    # 1. Points metadata
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

    # 2. 7-day forecast
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

    # 3. Current observations from nearest station
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

    # 4. Active alerts
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
    return render_template("index.html")


@app.route("/weather", methods=["POST"])
def weather():
    zipcode = request.form.get("zipcode", "").strip()
    lat_raw = request.form.get("lat", "").strip()
    lon_raw = request.form.get("lon", "").strip()

    location_label = None
    error = None

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
