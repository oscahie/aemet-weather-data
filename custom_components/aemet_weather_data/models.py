"""Typed data returned by AEMET's public XML documents."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Observation:
    time: datetime
    temperature: float | None
    wind_speed: float | None
    wind_direction: str | None
    wind_bearing: int | None
    gust_speed: float | None
    gust_direction: str | None
    gust_bearing: int | None
    precipitation: float | None
    pressure: float | None
    humidity: float | None
    pressure_tendency: float | None


@dataclass(frozen=True)
class Observations:
    station_id: str
    name: str
    generated_at: datetime
    readings: tuple[Observation, ...]

    @property
    def latest(self) -> Observation:
        return self.readings[-1]


@dataclass(frozen=True)
class DaySummary:
    date: date
    maximum_temperature: float | None = None
    minimum_temperature: float | None = None
    mean_temperature: float | None = None
    maximum_wind: float | None = None
    maximum_gust: float | None = None
    precipitation: float | None = None
    precipitation_00_06: float | None = None
    precipitation_06_12: float | None = None
    precipitation_12_18: float | None = None
    precipitation_18_24: float | None = None


@dataclass(frozen=True)
class DailyObservations:
    station_id: str
    name: str
    generated_at: datetime
    days: tuple[DaySummary, ...]

    @property
    def latest(self) -> DaySummary:
        return self.days[-1]


@dataclass(frozen=True)
class TodayObservations:
    station_id: str
    name: str
    generated_at: datetime
    date: date
    summary: DaySummary


@dataclass(frozen=True)
class ProbabilityWindow:
    start: datetime
    end: datetime
    probability: int


@dataclass(frozen=True)
class HourlyForecast:
    time: datetime
    condition: str | None = None
    temperature: float | None = None
    apparent_temperature: float | None = None
    humidity: float | None = None
    precipitation: float | None = None
    snow: float | None = None
    wind_speed: float | None = None
    wind_direction: str | None = None
    wind_bearing: int | None = None
    gust_speed: float | None = None


@dataclass(frozen=True)
class HourlyForecasts:
    city_id: str
    name: str
    issued_at: datetime
    hours: tuple[HourlyForecast, ...]
    probability_windows: tuple[ProbabilityWindow, ...]


@dataclass(frozen=True)
class DailyForecast:
    date: date
    condition: str | None = None
    maximum_temperature: float | None = None
    minimum_temperature: float | None = None
    maximum_apparent_temperature: float | None = None
    minimum_apparent_temperature: float | None = None
    maximum_humidity: float | None = None
    minimum_humidity: float | None = None
    precipitation_probability: int | None = None
    snow_line: float | None = None
    wind_speed: float | None = None
    wind_direction: str | None = None
    wind_bearing: int | None = None
    gust_speed: float | None = None
    uv_index: float | None = None


@dataclass(frozen=True)
class DailyForecasts:
    city_id: str
    name: str
    issued_at: datetime
    days: tuple[DailyForecast, ...]


@dataclass(frozen=True)
class Warning:
    title: str
    url: str


@dataclass(frozen=True)
class Warnings:
    zone_id: str
    name: str
    published_at: datetime | None
    items: tuple[Warning, ...]
