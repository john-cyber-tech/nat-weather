# National Weather Reader

A simple Flask web application that delivers plain-English weather reports for any US location using the free [National Weather Service API](https://www.weather.gov/documentation/services-web-api).

Enter a ZIP code and get:

- **Current conditions** — temperature, feels-like, humidity, wind, visibility, barometric pressure, and dew point
- **7-day forecast** — day and night periods with precipitation probability and detailed descriptions written by NWS meteorologists
- **Active weather alerts** — tornado warnings, flood watches, and other official alerts displayed prominently

No API key is required. All data comes from US government sources.

---

## Screenshots

| Search | Weather Report |
|--------|---------------|
| ![Search form](https://github.com/john-cyber-tech/nat-weather/assets/search.png) <img width="511" height="558" alt="weather" src="https://github.com/user-attachments/assets/096db35c-9194-47ab-9eec-3fa7cbdd4d53" />
| ![Weather report](https://github.com/john-cyber-tech/nat-weather/assets/report.png) <img width="892" height="974" alt="weatherscreen" src="https://github.com/user-attachments/assets/9edd7c26-7e12-41e3-85f9-c09fa0733c64" />
|

---

## Requirements

- Python 3.8 or higher
- An internet connection (the app calls external APIs at runtime)

---

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/john-cyber-tech/nat-weather.git
cd nat-weather
```

**2. Create and activate a virtual environment**

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Run the app**

```bash
python app.py
```

Open your browser to **http://127.0.0.1:5000**.

---

## Usage

1. Type a US ZIP code into the search box and click **Get Weather Report**.
2. Alternatively, expand the *or* section and enter a latitude and longitude directly.
3. Use the sample location buttons at the bottom of the form to try a few cities instantly.

---

## How It Works

```
User enters ZIP code
        │
        ▼
OpenStreetMap Nominatim API
(ZIP → latitude, longitude)
        │
        ▼
NWS /points/{lat},{lon}
(resolve grid + fetch endpoint URLs)
        │
        ├──▶ /gridpoints/.../forecast          7-day forecast
        ├──▶ /stations/{id}/observations/latest  current conditions
        └──▶ /alerts/active?point=...           active alerts
                │
                ▼
        Rendered in Flask template
```

All NWS forecast text is written by human meteorologists in plain English, so no AI or translation layer is needed to make it readable.

---

## Project Structure

```
nat-weather/
├── app.py              # Flask application and NWS API logic
├── requirements.txt    # Python dependencies
├── static/
│   └── style.css       # Application styles
└── templates/
    ├── base.html       # Shared layout (header, footer)
    ├── index.html      # Search form
    └── weather.html    # Weather report display
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| [Flask](https://flask.palletsprojects.com/) | Web framework |
| [Requests](https://requests.readthedocs.io/) | HTTP client for API calls |

---

## Data Sources

| Source | Used For | Cost |
|--------|----------|------|
| [National Weather Service API](https://api.weather.gov) | Forecasts, current conditions, alerts | Free |
| [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org) | ZIP code → coordinates | Free |

> **Note:** The NWS API only covers the United States and its territories. Entering a non-US location will display an error message.

---

## License

This project is released under the [MIT License](LICENSE).

Weather data is provided by the National Weather Service, a US government agency. Data is in the public domain.
