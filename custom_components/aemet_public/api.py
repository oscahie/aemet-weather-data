"""HTTP client for the public XML documents used by aemet.es."""

import asyncio
from datetime import date
import re
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientSession

from .models import (
    DailyForecasts,
    DailyObservations,
    HourlyForecasts,
    Observations,
    TodayObservations,
    Warnings,
)
from .parsers import (
    AemetFormatError,
    parse_daily_forecast,
    parse_daily_observations,
    parse_hourly_forecast,
    parse_observations,
    parse_today,
    parse_warnings,
)

BASE_URL = "https://www.aemet.es"
MAX_RESPONSE_BYTES = 2_000_000
_CITY = re.compile(r"^[0-9]{5}$")
_STATION = re.compile(r"^[A-Z0-9]{4,6}$")
_ZONE = re.compile(r"^[0-9]{6}$")


class AemetError(Exception):
    """A source could not be read or parsed."""


class AemetInvalidId(AemetError):
    """A configured ID does not exist at AEMET."""


class AemetPublicClient:
    """Fetch AEMET web data without a key or browser session."""

    def __init__(self, session: ClientSession, zone: ZoneInfo) -> None:
        self._session = session
        self._zone = zone

    async def _xml(self, path: str) -> bytes:
        try:
            async with asyncio.timeout(20):
                async with self._session.get(
                    f"{BASE_URL}{path}",
                    headers={"Accept": "application/xml, text/xml;q=0.9"},
                ) as response:
                    if response.status == 404:
                        raise AemetInvalidId(f"AEMET has no document at {path}")
                    response.raise_for_status()
                    if response.url.host != "www.aemet.es":
                        raise AemetError("Unexpected redirect from AEMET")
                    raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise AemetError("AEMET response is too large")
                    return raw
        except (TimeoutError, ClientError) as err:
            raise AemetError(f"AEMET request failed: {type(err).__name__}") from err

    async def observations(self, station_id: str) -> Observations:
        station_id = station_id.strip().upper()
        if not _STATION.fullmatch(station_id):
            raise AemetInvalidId("Invalid station ID")
        xml = await self._xml(f"/es/api-eltiempo/udat/tablas-graficas/horario/9/{station_id}")
        try:
            return parse_observations(xml, station_id)
        except AemetFormatError as err:
            raise AemetError(str(err)) from err

    async def today(self, station_id: str, day: date) -> TodayObservations:
        station_id = station_id.strip().upper()
        if not _STATION.fullmatch(station_id):
            raise AemetInvalidId("Invalid station ID")
        stamp = day.strftime("%Y%m%dT00000")
        xml = await self._xml(f"/es/api-eltiempo/udat/tablas-graficas/diario/9/{station_id}/{stamp}")
        try:
            return parse_today(xml, station_id, day)
        except AemetFormatError as err:
            raise AemetError(str(err)) from err

    async def daily_observations(self, station_id: str) -> DailyObservations:
        station_id = station_id.strip().upper()
        if not _STATION.fullmatch(station_id):
            raise AemetInvalidId("Invalid station ID")
        xml = await self._xml(f"/es/api-eltiempo/udat/tablas-graficas/diario/9/{station_id}")
        try:
            return parse_daily_observations(xml, station_id)
        except AemetFormatError as err:
            raise AemetError(str(err)) from err

    async def hourly_forecast(self, city_id: str) -> HourlyForecasts:
        if not _CITY.fullmatch(city_id):
            raise AemetInvalidId("Invalid municipality ID")
        xml = await self._xml(f"/xml/municipios_h/localidad_h_{city_id}.xml")
        try:
            return parse_hourly_forecast(xml, city_id, self._zone)
        except AemetFormatError as err:
            raise AemetError(str(err)) from err

    async def daily_forecast(self, city_id: str) -> DailyForecasts:
        if not _CITY.fullmatch(city_id):
            raise AemetInvalidId("Invalid municipality ID")
        xml = await self._xml(f"/xml/municipios/localidad_{city_id}.xml")
        try:
            return parse_daily_forecast(xml, city_id, self._zone)
        except AemetFormatError as err:
            raise AemetError(str(err)) from err

    async def warnings(self, zone_id: str) -> Warnings:
        if not _ZONE.fullmatch(zone_id):
            raise AemetInvalidId("Invalid warning-zone ID")
        xml = await self._xml(
            "/documentos_d/eltiempo/prediccion/avisos/rss/"
            f"CAP_AFAZ{zone_id}_RSS.xml"
        )
        try:
            return parse_warnings(xml, zone_id)
        except AemetFormatError as err:
            raise AemetError(str(err)) from err
