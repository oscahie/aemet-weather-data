"""Sensors backed by AEMET station data, municipal forecasts, and alerts."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTRIBUTION,
    CONF_CITY_NAME,
    CONF_STATION_NAME,
    DOMAIN,
    SOURCE_DAILY,
    SOURCE_DAILY_FORECAST,
    SOURCE_HOURLY_FORECAST,
    SOURCE_OBSERVATION,
    SOURCE_TODAY,
    SOURCE_WARNINGS,
)
from .coordinator import AemetCoordinator, AemetRuntime


@dataclass(frozen=True, kw_only=True)
class AemetSensorDescription(SensorEntityDescription):
    """A sensor's document, record selection, and data field."""

    source: str
    kind: str
    field: str


def _sensor(
    key: str,
    source: str,
    kind: str,
    field: str,
    unit: str | None = None,
    device_class: SensorDeviceClass | None = None,
    state_class: SensorStateClass | None = None,
    diagnostic: bool = False,
) -> AemetSensorDescription:
    return AemetSensorDescription(
        key=key,
        translation_key=key,
        source=source,
        kind=kind,
        field=field,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=state_class,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
    )


SENSORS: tuple[AemetSensorDescription, ...] = (
    _sensor("temperature", SOURCE_OBSERVATION, "observation", "temperature", "°C", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    _sensor("humidity", SOURCE_OBSERVATION, "observation", "humidity", "%", SensorDeviceClass.HUMIDITY, SensorStateClass.MEASUREMENT),
    _sensor("pressure", SOURCE_OBSERVATION, "observation", "pressure", "hPa", SensorDeviceClass.ATMOSPHERIC_PRESSURE, SensorStateClass.MEASUREMENT),
    _sensor("pressure_tendency", SOURCE_OBSERVATION, "observation", "pressure_tendency", "hPa"),
    _sensor("wind_speed", SOURCE_OBSERVATION, "observation", "wind_speed", "km/h", SensorDeviceClass.WIND_SPEED, SensorStateClass.MEASUREMENT),
    _sensor("wind_bearing", SOURCE_OBSERVATION, "observation", "wind_bearing", "°", SensorDeviceClass.WIND_DIRECTION, SensorStateClass.MEASUREMENT_ANGLE),
    _sensor("gust_speed", SOURCE_OBSERVATION, "observation", "gust_speed", "km/h", SensorDeviceClass.WIND_SPEED, SensorStateClass.MEASUREMENT),
    _sensor("gust_bearing", SOURCE_OBSERVATION, "observation", "gust_bearing", "°", SensorDeviceClass.WIND_DIRECTION, SensorStateClass.MEASUREMENT_ANGLE),
    _sensor("hourly_precipitation", SOURCE_OBSERVATION, "observation", "precipitation", "mm", SensorDeviceClass.PRECIPITATION),
    _sensor("observation_time", SOURCE_OBSERVATION, "observation", "time", device_class=SensorDeviceClass.TIMESTAMP, diagnostic=True),

    _sensor("today_maximum_temperature", SOURCE_TODAY, "today", "maximum_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("today_minimum_temperature", SOURCE_TODAY, "today", "minimum_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("today_maximum_wind", SOURCE_TODAY, "today", "maximum_wind", "km/h", SensorDeviceClass.WIND_SPEED),
    _sensor("today_maximum_gust", SOURCE_TODAY, "today", "maximum_gust", "km/h", SensorDeviceClass.WIND_SPEED),
    _sensor("today_precipitation", SOURCE_TODAY, "today", "precipitation", "mm", SensorDeviceClass.PRECIPITATION),

    _sensor("last_day_date", SOURCE_DAILY, "last_day", "date", device_class=SensorDeviceClass.DATE, diagnostic=True),
    _sensor("last_day_maximum_temperature", SOURCE_DAILY, "last_day", "maximum_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("last_day_minimum_temperature", SOURCE_DAILY, "last_day", "minimum_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("last_day_mean_temperature", SOURCE_DAILY, "last_day", "mean_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("last_day_maximum_wind", SOURCE_DAILY, "last_day", "maximum_wind", "km/h", SensorDeviceClass.WIND_SPEED),
    _sensor("last_day_maximum_gust", SOURCE_DAILY, "last_day", "maximum_gust", "km/h", SensorDeviceClass.WIND_SPEED),
    _sensor("last_day_precipitation", SOURCE_DAILY, "last_day", "precipitation", "mm", SensorDeviceClass.PRECIPITATION),
    _sensor("last_day_precipitation_00_06", SOURCE_DAILY, "last_day", "precipitation_00_06", "mm", SensorDeviceClass.PRECIPITATION),
    _sensor("last_day_precipitation_06_12", SOURCE_DAILY, "last_day", "precipitation_06_12", "mm", SensorDeviceClass.PRECIPITATION),
    _sensor("last_day_precipitation_12_18", SOURCE_DAILY, "last_day", "precipitation_12_18", "mm", SensorDeviceClass.PRECIPITATION),
    _sensor("last_day_precipitation_18_24", SOURCE_DAILY, "last_day", "precipitation_18_24", "mm", SensorDeviceClass.PRECIPITATION),

    _sensor("next_hour_time", SOURCE_HOURLY_FORECAST, "next_hour", "time", device_class=SensorDeviceClass.TIMESTAMP, diagnostic=True),
    _sensor("next_hour_condition", SOURCE_HOURLY_FORECAST, "next_hour", "condition"),
    _sensor("next_hour_temperature", SOURCE_HOURLY_FORECAST, "next_hour", "temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("next_hour_apparent_temperature", SOURCE_HOURLY_FORECAST, "next_hour", "apparent_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("next_hour_humidity", SOURCE_HOURLY_FORECAST, "next_hour", "humidity", "%", SensorDeviceClass.HUMIDITY),
    _sensor("next_hour_precipitation", SOURCE_HOURLY_FORECAST, "next_hour", "precipitation", "mm", SensorDeviceClass.PRECIPITATION),
    _sensor("next_hour_snow", SOURCE_HOURLY_FORECAST, "next_hour", "snow", "mm"),
    _sensor("next_hour_wind_speed", SOURCE_HOURLY_FORECAST, "next_hour", "wind_speed", "km/h", SensorDeviceClass.WIND_SPEED),
    _sensor("next_hour_wind_bearing", SOURCE_HOURLY_FORECAST, "next_hour", "wind_bearing", "°", SensorDeviceClass.WIND_DIRECTION, SensorStateClass.MEASUREMENT_ANGLE),
    _sensor("next_hour_gust_speed", SOURCE_HOURLY_FORECAST, "next_hour", "gust_speed", "km/h", SensorDeviceClass.WIND_SPEED),
    _sensor("current_precipitation_probability", SOURCE_HOURLY_FORECAST, "probability", "probability", "%"),

    _sensor("forecast_today_condition", SOURCE_DAILY_FORECAST, "forecast_today", "condition"),
    _sensor("forecast_today_maximum_temperature", SOURCE_DAILY_FORECAST, "forecast_today", "maximum_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("forecast_today_minimum_temperature", SOURCE_DAILY_FORECAST, "forecast_today", "minimum_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("forecast_today_maximum_apparent_temperature", SOURCE_DAILY_FORECAST, "forecast_today", "maximum_apparent_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("forecast_today_minimum_apparent_temperature", SOURCE_DAILY_FORECAST, "forecast_today", "minimum_apparent_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("forecast_today_maximum_humidity", SOURCE_DAILY_FORECAST, "forecast_today", "maximum_humidity", "%", SensorDeviceClass.HUMIDITY),
    _sensor("forecast_today_minimum_humidity", SOURCE_DAILY_FORECAST, "forecast_today", "minimum_humidity", "%", SensorDeviceClass.HUMIDITY),
    _sensor("forecast_today_precipitation_probability", SOURCE_DAILY_FORECAST, "forecast_today", "precipitation_probability", "%"),
    _sensor("forecast_today_uv_index", SOURCE_DAILY_FORECAST, "forecast_today", "uv_index"),
    _sensor("forecast_today_snow_line", SOURCE_DAILY_FORECAST, "forecast_today", "snow_line", "m", SensorDeviceClass.DISTANCE),
    _sensor("forecast_today_wind_speed", SOURCE_DAILY_FORECAST, "forecast_today", "wind_speed", "km/h", SensorDeviceClass.WIND_SPEED),
    _sensor("forecast_today_wind_bearing", SOURCE_DAILY_FORECAST, "forecast_today", "wind_bearing", "°", SensorDeviceClass.WIND_DIRECTION, SensorStateClass.MEASUREMENT_ANGLE),
    _sensor("forecast_today_gust_speed", SOURCE_DAILY_FORECAST, "forecast_today", "gust_speed", "km/h", SensorDeviceClass.WIND_SPEED),
    _sensor("forecast_tomorrow_condition", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "condition"),
    _sensor("forecast_tomorrow_maximum_temperature", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "maximum_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("forecast_tomorrow_minimum_temperature", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "minimum_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("forecast_tomorrow_maximum_apparent_temperature", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "maximum_apparent_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("forecast_tomorrow_minimum_apparent_temperature", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "minimum_apparent_temperature", "°C", SensorDeviceClass.TEMPERATURE),
    _sensor("forecast_tomorrow_maximum_humidity", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "maximum_humidity", "%", SensorDeviceClass.HUMIDITY),
    _sensor("forecast_tomorrow_minimum_humidity", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "minimum_humidity", "%", SensorDeviceClass.HUMIDITY),
    _sensor("forecast_tomorrow_precipitation_probability", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "precipitation_probability", "%"),
    _sensor("forecast_tomorrow_uv_index", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "uv_index"),
    _sensor("forecast_tomorrow_snow_line", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "snow_line", "m", SensorDeviceClass.DISTANCE),
    _sensor("forecast_tomorrow_wind_speed", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "wind_speed", "km/h", SensorDeviceClass.WIND_SPEED),
    _sensor("forecast_tomorrow_wind_bearing", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "wind_bearing", "°", SensorDeviceClass.WIND_DIRECTION, SensorStateClass.MEASUREMENT_ANGLE),
    _sensor("forecast_tomorrow_gust_speed", SOURCE_DAILY_FORECAST, "forecast_tomorrow", "gust_speed", "km/h", SensorDeviceClass.WIND_SPEED),

    _sensor("warning_count", SOURCE_WARNINGS, "warnings", "count"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create only the sensors relevant to the configured sources."""
    runtime: AemetRuntime = entry.runtime_data
    async_add_entities(
        AemetSensor(entry, runtime, description)
        for description in SENSORS
        if runtime.coordinator(description.source) is not None
    )


class AemetSensor(CoordinatorEntity[AemetCoordinator], SensorEntity):
    """A single field from an independently fresh AEMET document."""

    _attr_has_entity_name = True

    def __init__(
        self, entry: ConfigEntry, runtime: AemetRuntime, description: AemetSensorDescription
    ) -> None:
        coordinator = runtime.coordinator(description.source)
        assert coordinator is not None
        super().__init__(coordinator)
        self.entity_description = description
        self._runtime = runtime
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        if description.source in (SOURCE_OBSERVATION, SOURCE_TODAY, SOURCE_DAILY):
            suffix = "station"
            name = entry.data.get(CONF_STATION_NAME) or runtime.station_id
            url = f"https://www.aemet.es/es/eltiempo/observacion/ultimosdatos?l={runtime.station_id}"
        elif description.source == SOURCE_WARNINGS:
            suffix = "warnings"
            name = f"Avisos {runtime.warning_zone}"
            url = f"https://www.aemet.es/es/eltiempo/prediccion/avisos?l={runtime.warning_zone}"
        else:
            suffix = "municipality"
            name = entry.data.get(CONF_CITY_NAME) or runtime.city_id
            url = "https://www.aemet.es/es/eltiempo/prediccion/municipios"
        self._source_url = url
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id}_{suffix}")},
            name=f"AEMET {name}",
            configuration_url=url,
            model="Public web data",
        )

    def _record(self) -> Any | None:
        description = self.entity_description
        source = description.source
        value = self._runtime.source_data(source)
        if value is None:
            return None
        kind = description.kind
        if kind == "observation":
            return value.latest
        if kind == "today":
            return value.summary
        if kind == "last_day":
            return value.latest
        if kind == "next_hour":
            return self._runtime.next_hour()
        if kind == "forecast_today":
            return self._runtime.day_forecast()
        if kind == "forecast_tomorrow":
            return self._runtime.day_forecast(1)
        if kind == "probability":
            return self._runtime.probability_window()
        if kind == "warnings":
            return value
        return None

    @property
    def native_value(self) -> Any | None:
        """Return a value only while its source is usable and the field exists."""
        record = self._record()
        if record is None:
            return None
        if self.entity_description.kind == "warnings":
            return len(record.items)
        return getattr(record, self.entity_description.field, None)

    @property
    def available(self) -> bool:
        """A missing field is unavailable, not a fabricated zero."""
        return self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose provenance and the actual measurement/forecast date."""
        attrs: dict[str, Any] = {"attribution": ATTRIBUTION, "source_url": self._source_url}
        source = self.entity_description.source
        snapshot = self._runtime.snapshot(source)
        if snapshot is not None:
            attrs["last_received_at"] = snapshot.fetched_at.isoformat()
            if (generated := getattr(snapshot.value, "generated_at", None)) is not None:
                attrs["document_generated_at"] = generated.isoformat()
            if (issued := getattr(snapshot.value, "issued_at", None)) is not None:
                attrs["document_issued_at"] = issued.isoformat()
        value = self._runtime.source_data(source)
        record = self._record()
        if value is None or record is None:
            return attrs
        if source == SOURCE_OBSERVATION:
            attrs["sample_time"] = value.latest.time.isoformat()
            attrs["wind_direction"] = value.latest.wind_direction
            attrs["gust_direction"] = value.latest.gust_direction
            if self.entity_description.key == "observation_time":
                attrs["hourly_samples"] = len(value.readings)
        elif source == SOURCE_TODAY:
            attrs["date"] = value.date.isoformat()
        elif source == SOURCE_DAILY:
            attrs["date"] = value.latest.date.isoformat()
            if self.entity_description.key == "last_day_date":
                attrs["previous_days"] = [
                    {"date": day.date.isoformat(), "maximum_temperature": day.maximum_temperature,
                     "minimum_temperature": day.minimum_temperature, "mean_temperature": day.mean_temperature,
                     "precipitation": day.precipitation}
                    for day in value.days
                ]
        elif source == SOURCE_HOURLY_FORECAST:
            attrs["issued_at"] = value.issued_at.isoformat()
            if self.entity_description.kind == "probability":
                attrs["period_start"] = record.start.isoformat()
                attrs["period_end"] = record.end.isoformat()
            else:
                attrs["forecast_time"] = record.time.isoformat()
                attrs["wind_direction"] = record.wind_direction
        elif source == SOURCE_DAILY_FORECAST:
            attrs["issued_at"] = value.issued_at.isoformat()
            attrs["forecast_date"] = record.date.isoformat()
            attrs["wind_direction"] = record.wind_direction
        elif source == SOURCE_WARNINGS:
            attrs["published_at"] = value.published_at.isoformat() if value.published_at else None
            attrs["warnings"] = [
                {"title": warning.title, "url": warning.url} for warning in value.items[:20]
            ]
        return attrs
