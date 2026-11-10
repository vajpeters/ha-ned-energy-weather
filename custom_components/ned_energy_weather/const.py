"""Integration constants."""

from zoneinfo import ZoneInfo

DOMAIN = "ned_energy_weather"
NAME = "NED Energieweerbericht"
API_URL = "https://api.ned.nl/v1/utilizations"
AMSTERDAM = ZoneInfo("Europe/Amsterdam")
PROVINCES = dict(
    enumerate(
        (
            "Groningen",
            "Friesland",
            "Drenthe",
            "Overijssel",
            "Flevoland",
            "Gelderland",
            "Utrecht",
            "Noord-Holland",
            "Zuid-Holland",
            "Zeeland",
            "Noord-Brabant",
            "Limburg",
        ),
        1,
    )
)
DEFAULT_PROVINCE = 7
INTERVALS = (15, 30, 60, 120, 360)
DEFAULT_INTERVAL = 60
UNITS = {
    "capacity": "kW",
    "volume": "kWh",
    "percentage": "%",
    "emission": "kg",
    "emission_factor": "kg/kWh",
}
GRANULARITIES = {"15min": 4, "hour": 5, "day": 6}
CLASSIFICATIONS = {"actual": 2, "forecast": 1}
RESOURCE = f"/api/{DOMAIN}/ned-energy-weather-card.js"
