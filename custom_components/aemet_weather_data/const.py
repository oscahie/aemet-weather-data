"""Constants for AEMET Public Weather."""

from datetime import timedelta

DOMAIN = "aemet_weather_data"
CONF_CITY_ID = "city_id"
CONF_STATION_ID = "station_id"
CONF_WARNING_ZONE = "warning_zone"
CONF_TIME_ZONE = "time_zone"
CONF_CITY_NAME = "city_name"
CONF_STATION_NAME = "station_name"

DEFAULT_TIME_ZONE = "Europe/Madrid"
TIME_ZONES = ("Europe/Madrid", "Atlantic/Canary")

OBSERVATION_INTERVAL = timedelta(minutes=15)
FORECAST_INTERVAL = timedelta(hours=1)
WARNING_INTERVAL = timedelta(minutes=30)

OBSERVATION_MAX_AGE = timedelta(hours=2)
TODAY_MAX_AGE = timedelta(hours=2)
DAILY_MAX_AGE = timedelta(hours=48)
FORECAST_ISSUE_MAX_AGE = timedelta(hours=36)
FORECAST_FETCH_MAX_AGE = timedelta(hours=3)
WARNING_FETCH_MAX_AGE = timedelta(hours=2)

SOURCE_OBSERVATION = "observation"
SOURCE_TODAY = "today"
SOURCE_DAILY = "daily"
SOURCE_HOURLY_FORECAST = "hourly_forecast"
SOURCE_DAILY_FORECAST = "daily_forecast"
SOURCE_WARNINGS = "warnings"

ATTRIBUTION = "Fuente: AEMET"
