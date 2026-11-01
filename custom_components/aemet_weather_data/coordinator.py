"""Independent update schedules and freshness checks for AEMET sources."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AemetWeatherDataClient
from .const import (
    DAILY_MAX_AGE,
    FORECAST_FETCH_MAX_AGE,
    FORECAST_ISSUE_MAX_AGE,
    OBSERVATION_MAX_AGE,
    SOURCE_DAILY,
    SOURCE_DAILY_FORECAST,
    SOURCE_HOURLY_FORECAST,
    SOURCE_OBSERVATION,
    SOURCE_TODAY,
    SOURCE_WARNINGS,
    TODAY_MAX_AGE,
    WARNING_FETCH_MAX_AGE,
)
from .models import (
    DailyForecast,
    DailyForecasts,
    DailyObservations,
    HourlyForecast,
    HourlyForecasts,
    Observations,
    ProbabilityWindow,
    TodayObservations,
    Warnings,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceSnapshot:
    """One successfully received document and its fetch time."""

    value: Any
    fetched_at: datetime


class AemetCoordinator(DataUpdateCoordinator[dict[str, SourceSnapshot]]):
    """Fetch related documents, preserving healthy sources independently."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        name: str,
        interval: timedelta,
        fetchers: dict[str, Callable[[], Awaitable[Any]]],
    ) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=name, update_interval=interval)
        self._fetchers = fetchers
        self._failed: set[str] = set()

    async def _async_update_data(self) -> dict[str, SourceSnapshot]:
        results = await asyncio.gather(
            *(fetcher() for fetcher in self._fetchers.values()),
            return_exceptions=True,
        )
        current = dict(self.data or {})
        fetched_at = datetime.now(UTC)
        for source, result in zip(self._fetchers, results, strict=True):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, Exception):
                if source not in self._failed:
                    _LOGGER.warning("AEMET source %s failed: %s", source, result)
                self._failed.add(source)
                continue
            if source in self._failed:
                _LOGGER.info("AEMET source %s recovered", source)
            self._failed.discard(source)
            current[source] = SourceSnapshot(result, fetched_at)
        if not current:
            raise UpdateFailed("All configured AEMET sources failed")
        return current


@dataclass
class AemetRuntime:
    """The config entry's data and coordinators."""

    client: AemetWeatherDataClient
    zone: ZoneInfo
    city_id: str
    station_id: str
    warning_zone: str
    observation_coordinator: AemetCoordinator | None
    forecast_coordinator: AemetCoordinator | None
    warning_coordinator: AemetCoordinator | None

    def coordinator(self, source: str) -> AemetCoordinator | None:
        if source in (SOURCE_OBSERVATION, SOURCE_TODAY, SOURCE_DAILY):
            return self.observation_coordinator
        if source in (SOURCE_HOURLY_FORECAST, SOURCE_DAILY_FORECAST):
            return self.forecast_coordinator
        if source == SOURCE_WARNINGS:
            return self.warning_coordinator
        return None

    def snapshot(self, source: str) -> SourceSnapshot | None:
        coordinator = self.coordinator(source)
        return coordinator.data.get(source) if coordinator and coordinator.data else None

    def source_data(self, source: str) -> Any | None:
        """Return only data that is still meaningful now."""
        snapshot = self.snapshot(source)
        if snapshot is None:
            return None
        now = datetime.now(UTC)
        age = now - snapshot.fetched_at
        if age < timedelta(0):
            return None
        value = snapshot.value
        local_day = now.astimezone(self.zone).date()
        if source == SOURCE_OBSERVATION:
            return value if isinstance(value, Observations) and timedelta(0) <= now - value.latest.time <= OBSERVATION_MAX_AGE and timedelta(0) <= now - value.generated_at <= OBSERVATION_MAX_AGE else None
        if source == SOURCE_TODAY:
            return value if isinstance(value, TodayObservations) and value.date == local_day and age <= TODAY_MAX_AGE and timedelta(0) <= now - value.generated_at <= TODAY_MAX_AGE else None
        if source == SOURCE_DAILY:
            return value if isinstance(value, DailyObservations) and age <= DAILY_MAX_AGE and 0 <= (local_day - value.latest.date).days <= 3 and timedelta(0) <= now - value.generated_at <= DAILY_MAX_AGE else None
        if source == SOURCE_HOURLY_FORECAST:
            return value if isinstance(value, HourlyForecasts) and age <= FORECAST_FETCH_MAX_AGE and -timedelta(minutes=15) <= now - value.issued_at <= FORECAST_ISSUE_MAX_AGE and any(hour.time >= now for hour in value.hours) else None
        if source == SOURCE_DAILY_FORECAST:
            return value if isinstance(value, DailyForecasts) and age <= FORECAST_FETCH_MAX_AGE and -timedelta(minutes=15) <= now - value.issued_at <= FORECAST_ISSUE_MAX_AGE and value.days[-1].date >= local_day else None
        if source == SOURCE_WARNINGS:
            return value if isinstance(value, Warnings) and age <= WARNING_FETCH_MAX_AGE else None
        return None

    def next_hour(self) -> HourlyForecast | None:
        forecast = self.source_data(SOURCE_HOURLY_FORECAST)
        if forecast is None:
            return None
        now = datetime.now(UTC)
        return next((hour for hour in forecast.hours if hour.time >= now), None)

    def day_forecast(self, offset: int = 0) -> DailyForecast | None:
        forecast = self.source_data(SOURCE_DAILY_FORECAST)
        if forecast is None:
            return None
        day = datetime.now(UTC).astimezone(self.zone).date() + timedelta(days=offset)
        return next((item for item in forecast.days if item.date == day), None)

    def probability_window(self) -> ProbabilityWindow | None:
        forecast = self.source_data(SOURCE_HOURLY_FORECAST)
        if forecast is None:
            return None
        now = datetime.now(UTC)
        return next((window for window in forecast.probability_windows if window.start <= now < window.end), None)
