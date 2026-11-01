"""AEMET public XML integration for Home Assistant."""

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AemetPublicClient
from .const import (
    CONF_CITY_ID,
    CONF_STATION_ID,
    CONF_TIME_ZONE,
    CONF_WARNING_ZONE,
    DEFAULT_TIME_ZONE,
    DOMAIN,
    FORECAST_INTERVAL,
    OBSERVATION_INTERVAL,
    SOURCE_DAILY,
    SOURCE_DAILY_FORECAST,
    SOURCE_HOURLY_FORECAST,
    SOURCE_OBSERVATION,
    SOURCE_TODAY,
    SOURCE_WARNINGS,
    WARNING_INTERVAL,
)
from .coordinator import AemetCoordinator, AemetRuntime


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration domain."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one selected station, municipality, and optional warning zone."""
    zone = ZoneInfo(entry.data.get(CONF_TIME_ZONE, DEFAULT_TIME_ZONE))
    client = AemetPublicClient(async_get_clientsession(hass), zone)
    city_id = entry.data.get(CONF_CITY_ID, "")
    station_id = entry.data.get(CONF_STATION_ID, "")
    warning_zone = entry.data.get(CONF_WARNING_ZONE, "")

    observation_coordinator = None
    if station_id:
        observation_coordinator = AemetCoordinator(
            hass, entry, f"{DOMAIN}_{entry.entry_id}_observations", OBSERVATION_INTERVAL,
            {
                SOURCE_OBSERVATION: lambda: client.observations(station_id),
                SOURCE_TODAY: lambda: client.today(
                    station_id, datetime.now(UTC).astimezone(zone).date()
                ),
                SOURCE_DAILY: lambda: client.daily_observations(station_id),
            },
        )

    forecast_coordinator = None
    if city_id:
        forecast_coordinator = AemetCoordinator(
            hass, entry, f"{DOMAIN}_{entry.entry_id}_forecasts", FORECAST_INTERVAL,
            {
                SOURCE_HOURLY_FORECAST: lambda: client.hourly_forecast(city_id),
                SOURCE_DAILY_FORECAST: lambda: client.daily_forecast(city_id),
            },
        )

    warning_coordinator = None
    if warning_zone:
        warning_coordinator = AemetCoordinator(
            hass, entry, f"{DOMAIN}_{entry.entry_id}_warnings", WARNING_INTERVAL,
            {SOURCE_WARNINGS: lambda: client.warnings(warning_zone)},
        )

    runtime = AemetRuntime(
        client, zone, city_id, station_id, warning_zone,
        observation_coordinator, forecast_coordinator, warning_coordinator,
    )
    entry.runtime_data = runtime

    coordinators = tuple(coordinator for coordinator in (
        observation_coordinator, forecast_coordinator, warning_coordinator
    ) if coordinator is not None)
    await asyncio.gather(*(coordinator.async_refresh() for coordinator in coordinators))
    if not any(coordinator.data for coordinator in coordinators):
        raise ConfigEntryNotReady("No AEMET source is currently available")

    platforms = [Platform.SENSOR]
    if city_id:
        platforms.append(Platform.WEATHER)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities when the integration is reconfigured or removed."""
    platforms = [Platform.SENSOR]
    if entry.data.get(CONF_CITY_ID):
        platforms.append(Platform.WEATHER)
    return await hass.config_entries.async_unload_platforms(entry, platforms)
