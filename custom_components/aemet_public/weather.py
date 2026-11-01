"""Weather entity with station measurements and municipal forecasts."""

from datetime import UTC, datetime, time
from typing import Any

from homeassistant.components.weather import Forecast, WeatherEntity, WeatherEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTRIBUTION,
    CONF_CITY_NAME,
    DOMAIN,
    SOURCE_DAILY_FORECAST,
    SOURCE_HOURLY_FORECAST,
    SOURCE_OBSERVATION,
)
from .coordinator import AemetRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one weather entity for the configured municipality."""
    runtime: AemetRuntime = entry.runtime_data
    async_add_entities([AemetWeather(entry, runtime)])


class AemetWeather(WeatherEntity):
    """Current station conditions when present; forecast for municipality."""

    _attr_has_entity_name = True
    _attr_translation_key = "current_and_forecast"
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY
    )
    _attr_native_temperature_unit = "°C"
    _attr_native_pressure_unit = "hPa"
    _attr_native_wind_speed_unit = "km/h"
    _attr_native_precipitation_unit = "mm"

    def __init__(self, entry: ConfigEntry, runtime: AemetRuntime) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{entry.unique_id}_weather"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id}_municipality")},
            name=f"AEMET Forecast {entry.data.get(CONF_CITY_NAME) or runtime.city_id}",
            configuration_url="https://www.aemet.es/es/eltiempo/prediccion/municipios",
            model="Public web data",
        )

    async def async_added_to_hass(self) -> None:
        """Listen to both feeds without making a network request per entity."""
        await super().async_added_to_hass()
        for coordinator in (
            self._runtime.observation_coordinator,
            self._runtime.forecast_coordinator,
        ):
            if coordinator is not None:
                self.async_on_remove(coordinator.async_add_listener(self._handle_source_update))

    @callback
    def _handle_source_update(self) -> None:
        self.async_write_ha_state()
        self.hass.async_create_task(self.async_update_listeners(None))

    @property
    def available(self) -> bool:
        return (
            self._runtime.source_data(SOURCE_OBSERVATION) is not None
            or self._runtime.source_data(SOURCE_HOURLY_FORECAST) is not None
            or self._runtime.source_data(SOURCE_DAILY_FORECAST) is not None
        )

    @property
    def condition(self) -> str | None:
        hour = self._runtime.next_hour()
        if hour and hour.condition:
            return hour.condition
        day = self._runtime.day_forecast()
        return day.condition if day else None

    @property
    def native_temperature(self) -> float | None:
        observed = self._runtime.source_data(SOURCE_OBSERVATION)
        if observed and observed.latest.temperature is not None:
            return observed.latest.temperature
        hour = self._runtime.next_hour()
        return hour.temperature if hour else None

    @property
    def native_apparent_temperature(self) -> float | None:
        hour = self._runtime.next_hour()
        return hour.apparent_temperature if hour else None

    @property
    def humidity(self) -> float | None:
        observed = self._runtime.source_data(SOURCE_OBSERVATION)
        if observed and observed.latest.humidity is not None:
            return observed.latest.humidity
        hour = self._runtime.next_hour()
        return hour.humidity if hour else None

    @property
    def native_pressure(self) -> float | None:
        observed = self._runtime.source_data(SOURCE_OBSERVATION)
        return observed.latest.pressure if observed else None

    @property
    def native_wind_speed(self) -> float | None:
        observed = self._runtime.source_data(SOURCE_OBSERVATION)
        if observed and observed.latest.wind_speed is not None:
            return observed.latest.wind_speed
        hour = self._runtime.next_hour()
        return hour.wind_speed if hour else None

    @property
    def native_wind_gust_speed(self) -> float | None:
        observed = self._runtime.source_data(SOURCE_OBSERVATION)
        if observed and observed.latest.gust_speed is not None:
            return observed.latest.gust_speed
        hour = self._runtime.next_hour()
        return hour.gust_speed if hour else None

    @property
    def wind_bearing(self) -> int | None:
        observed = self._runtime.source_data(SOURCE_OBSERVATION)
        if observed and observed.latest.wind_bearing is not None:
            return observed.latest.wind_bearing
        hour = self._runtime.next_hour()
        return hour.wind_bearing if hour else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        observed = self._runtime.source_data(SOURCE_OBSERVATION)
        hourly = self._runtime.source_data(SOURCE_HOURLY_FORECAST)
        daily = self._runtime.source_data(SOURCE_DAILY_FORECAST)
        return {
            "attribution": ATTRIBUTION,
            "station_id": self._runtime.station_id or None,
            "municipality_id": self._runtime.city_id,
            "observation_time": observed.latest.time.isoformat() if observed else None,
            "forecast_issued_at": (
                hourly.issued_at.isoformat() if hourly else
                daily.issued_at.isoformat() if daily else None
            ),
            "temperature_source": (
                "station" if observed and observed.latest.temperature is not None
                else "forecast" if self._runtime.next_hour() is not None else None
            ),
        }

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Use the already cached forecast; probability windows are not hourly."""
        source = self._runtime.source_data(SOURCE_HOURLY_FORECAST)
        if source is None:
            return None
        now = datetime.now(UTC)
        return [
            Forecast(
                datetime=item.time.isoformat(),
                condition=item.condition,
                native_temperature=item.temperature,
                native_apparent_temperature=item.apparent_temperature,
                humidity=item.humidity,
                native_precipitation=item.precipitation,
                native_wind_speed=item.wind_speed,
                native_wind_gust_speed=item.gust_speed,
                wind_bearing=item.wind_bearing,
            )
            for item in source.hours if item.time >= now
        ]

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Keep daily rain probability on its original full-day interval."""
        source = self._runtime.source_data(SOURCE_DAILY_FORECAST)
        if source is None:
            return None
        today = datetime.now(UTC).astimezone(self._runtime.zone).date()
        return [
            Forecast(
                datetime=datetime.combine(item.date, time.min, self._runtime.zone).astimezone(UTC).isoformat(),
                condition=item.condition,
                native_temperature=item.maximum_temperature,
                native_templow=item.minimum_temperature,
                precipitation_probability=item.precipitation_probability,
                native_wind_speed=item.wind_speed,
                native_wind_gust_speed=item.gust_speed,
                wind_bearing=item.wind_bearing,
                uv_index=item.uv_index,
            )
            for item in source.days if item.date >= today
        ]
