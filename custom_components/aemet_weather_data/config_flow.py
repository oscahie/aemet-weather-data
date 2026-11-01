"""UI setup and reconfiguration for AEMET public data."""

import logging
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

from .api import AemetError, AemetInvalidId, AemetWeatherDataClient
from .const import (
    CONF_CITY_ID,
    CONF_CITY_NAME,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_TIME_ZONE,
    CONF_WARNING_ZONE,
    DEFAULT_TIME_ZONE,
    DOMAIN,
    TIME_ZONES,
)

SCHEMA = vol.Schema({
    vol.Optional(CONF_CITY_ID): str,
    vol.Optional(CONF_STATION_ID): str,
    vol.Optional(CONF_WARNING_ZONE): str,
    vol.Optional(CONF_TIME_ZONE, default=DEFAULT_TIME_ZONE): vol.In(TIME_ZONES),
})


class AemetWeatherDataConfigFlow(ConfigFlow, domain=DOMAIN):
    """Allow a municipality, station, or both to be selected by their AEMET IDs."""

    VERSION = 1

    def _duplicate(self, city_id: str, station_id: str, own_entry_id: str | None = None) -> bool:
        return any(
            entry.entry_id != own_entry_id
            and entry.data.get(CONF_CITY_ID, "") == city_id
            and entry.data.get(CONF_STATION_ID, "") == station_id
            for entry in self._async_current_entries()
        )

    async def _validate(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        errors: dict[str, str] = {}
        city_id = user_input.get(CONF_CITY_ID, "").strip()
        station_id = user_input.get(CONF_STATION_ID, "").strip().upper()
        warning_zone = user_input.get(CONF_WARNING_ZONE, "").strip()
        time_zone = user_input.get(CONF_TIME_ZONE, DEFAULT_TIME_ZONE)
        normalized = {
            CONF_CITY_ID: city_id,
            CONF_STATION_ID: station_id,
            CONF_WARNING_ZONE: warning_zone,
            CONF_TIME_ZONE: time_zone,
        }
        if not city_id and not station_id:
            return normalized, {"base": "no_location"}

        client = AemetWeatherDataClient(async_get_clientsession(self.hass), ZoneInfo(time_zone))
        city_name = ""
        station_name = ""
        if city_id:
            try:
                city_name = (await client.daily_forecast(city_id)).name
                await client.hourly_forecast(city_id)
            except AemetInvalidId:
                errors[CONF_CITY_ID] = "invalid_id"
            except AemetError as err:
                _LOGGER.warning("AEMET municipality validation failed: %s", err)
                errors["base"] = "cannot_connect"
        if station_id:
            try:
                station_name = (await client.observations(station_id)).name
            except AemetInvalidId:
                errors[CONF_STATION_ID] = "invalid_id"
            except AemetError as err:
                _LOGGER.warning("AEMET station validation failed: %s", err)
                errors["base"] = "cannot_connect"
        if warning_zone:
            try:
                await client.warnings(warning_zone)
            except AemetInvalidId:
                errors[CONF_WARNING_ZONE] = "invalid_id"
            except AemetError as err:
                _LOGGER.warning("AEMET warning-zone validation failed: %s", err)
                errors["base"] = "cannot_connect"
        normalized[CONF_CITY_NAME] = city_name
        normalized[CONF_STATION_NAME] = station_name
        return normalized, errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a new location."""
        errors: dict[str, str] = {}
        if user_input is not None:
            normalized, errors = await self._validate(user_input)
            if not errors:
                if self._duplicate(normalized[CONF_CITY_ID], normalized[CONF_STATION_ID]):
                    return self.async_abort(reason="already_configured")
                await self.async_set_unique_id(uuid4().hex)
                title = normalized[CONF_STATION_NAME] or normalized[CONF_CITY_NAME]
                return self.async_create_entry(title=f"AEMET {title}", data=normalized)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the selected AEMET sources while keeping entity IDs."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            normalized, errors = await self._validate(user_input)
            if not errors:
                if self._duplicate(
                    normalized[CONF_CITY_ID], normalized[CONF_STATION_ID], entry.entry_id
                ):
                    errors["base"] = "already_configured"
                else:
                    return self.async_update_reload_and_abort(entry, data_updates=normalized)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, entry.data),
            errors=errors,
        )
