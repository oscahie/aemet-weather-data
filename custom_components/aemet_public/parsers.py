"""Parse AEMET's public XML without depending on Home Assistant."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
import re
import unicodedata
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from .models import (
    DailyForecast,
    DailyForecasts,
    DailyObservations,
    DaySummary,
    HourlyForecast,
    HourlyForecasts,
    Observation,
    Observations,
    ProbabilityWindow,
    TodayObservations,
    Warning,
    Warnings,
)


class AemetFormatError(ValueError):
    """AEMET returned an unexpected or invalid document."""


_BEARINGS = {
    "N": 0, "NNE": 22, "NE": 45, "ENE": 67, "E": 90,
    "ESE": 112, "SE": 135, "SSE": 157, "S": 180,
    "SSO": 202, "SO": 225, "OSO": 247, "O": 270,
    "ONO": 292, "NO": 315, "NNO": 337,
    "SSW": 202, "SW": 225, "WSW": 247, "W": 270,
    "WNW": 292, "NW": 315, "NNW": 337,
}
_HOUR = re.compile(r"^\d{2}$")
_WINDOW = re.compile(r"^\d{4}$")


def _root(xml: str | bytes) -> ET.Element:
    if (b"<!DOCTYPE" if isinstance(xml, bytes) else "<!DOCTYPE") in xml.upper():
        raise AemetFormatError("XML document type is not allowed")
    try:
        return ET.fromstring(xml)
    except ET.ParseError as err:
        raise AemetFormatError("Invalid XML") from err


def _text(value: str | None) -> str:
    """Repair UTF-8 text mislabeled ISO-8859-15 in some AEMET XML files."""
    if not value:
        return ""
    if "Ã" in value or "Â" in value:
        try:
            return value.encode("latin-1").decode("utf-8")
        except (UnicodeError, ValueError):
            pass
    return value


def _number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError as err:
        raise AemetFormatError("Invalid numeric value") from err


def _integer(value: str | None) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _utc(value: str | None) -> datetime:
    if not value:
        raise AemetFormatError("Missing UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as err:
        raise AemetFormatError("Invalid UTC timestamp") from err
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _issued(root: ET.Element, zone: ZoneInfo) -> datetime:
    value = root.findtext("elaborado")
    if not value:
        raise AemetFormatError("Missing forecast issue time")
    try:
        return datetime.fromisoformat(value).replace(tzinfo=zone).astimezone(UTC)
    except ValueError as err:
        raise AemetFormatError("Invalid forecast issue time") from err


def _station(root: ET.Element, station_id: str) -> ET.Element:
    station = root.find("estacion")
    if station is None or station.get("id_c") != station_id:
        raise AemetFormatError("Unexpected station identifier")
    return station


def _city(root: ET.Element, city_id: str) -> None:
    if root.get("id") != city_id:
        raise AemetFormatError("Unexpected municipality identifier")


def _direction(value: str | None) -> tuple[str | None, int | None]:
    if not value or not value.strip():
        return None, None
    cardinal = value.strip().upper()
    return cardinal, _BEARINGS.get(cardinal)


def _day(value: str | None) -> date:
    if not value:
        raise AemetFormatError("Missing date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as err:
        raise AemetFormatError("Invalid date") from err


def _summary(element: ET.Element, day: date) -> DaySummary:
    return DaySummary(
        date=day,
        maximum_temperature=_number(element.findtext("tmax")),
        minimum_temperature=_number(element.findtext("tmin")),
        mean_temperature=_number(element.findtext("tmed")),
        maximum_wind=_number(element.findtext("vmax")),
        maximum_gust=_number(element.findtext("racha")),
        precipitation=_number(element.findtext("pre_0024")),
        precipitation_00_06=_number(element.findtext("pre_0006")),
        precipitation_06_12=_number(element.findtext("pre_0612")),
        precipitation_12_18=_number(element.findtext("pre_1218")),
        precipitation_18_24=_number(element.findtext("pre_1824")),
    )


def parse_observations(xml: str | bytes, station_id: str) -> Observations:
    """Read the last 24 hourly station measurements."""
    root = _root(xml)
    station = _station(root, station_id)
    generated_at = _utc(root.find("elaborado").get("utc") if root.find("elaborado") is not None else None)
    readings: list[Observation] = []
    for item in station.findall("periodo"):
        wind, bearing = _direction(item.findtext("dir_viento"))
        gust, gust_bearing = _direction(item.findtext("dir_racha"))
        readings.append(
            Observation(
                time=_utc(item.get("utc")),
                temperature=_number(item.findtext("temperatura")),
                wind_speed=_number(item.findtext("vel_viento")),
                wind_direction=wind,
                wind_bearing=bearing,
                gust_speed=_number(item.findtext("vel_racha")),
                gust_direction=gust,
                gust_bearing=gust_bearing,
                precipitation=_number(item.findtext("precipitacion")),
                pressure=_number(item.findtext("presion")),
                humidity=_number(item.findtext("humedad")),
                pressure_tendency=_number(item.findtext("tendencia")),
            )
        )
    if not readings:
        raise AemetFormatError("No hourly observations")
    readings.sort(key=lambda reading: reading.time)
    return Observations(station_id, _text(station.get("nombre")) or station_id, generated_at, tuple(readings))


def parse_today(xml: str | bytes, station_id: str, day: date) -> TodayObservations:
    """Read the in-progress daily extrema and rain total."""
    root = _root(xml)
    station = _station(root, station_id)
    generated_at = _utc(root.find("elaborado").get("utc") if root.find("elaborado") is not None else None)
    return TodayObservations(
        station_id, _text(station.get("nombre")) or station_id, generated_at, day,
        _summary(station, day),
    )


def parse_daily_observations(xml: str | bytes, station_id: str) -> DailyObservations:
    """Read AEMET's last seven completed daily summaries."""
    root = _root(xml)
    station = _station(root, station_id)
    generated_at = _utc(root.find("elaborado").get("utc") if root.find("elaborado") is not None else None)
    days = tuple(sorted(
        (_summary(item, _day(item.get("local"))) for item in station.findall("periodo")),
        key=lambda item: item.date,
    ))
    if not days:
        raise AemetFormatError("No daily observations")
    return DailyObservations(station_id, _text(station.get("nombre")) or station_id, generated_at, days)


def _condition(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    description = _text(element.get("descripcion", "")).strip().lower()
    if not description:
        return None
    normalized = "".join(
        char for char in unicodedata.normalize("NFD", description)
        if unicodedata.category(char) != "Mn"
    )
    if "tormenta" in normalized:
        return "lightning-rainy" if "lluv" in normalized or "chubasc" in normalized else "lightning"
    if "aguanieve" in normalized or ("nieve" in normalized and "lluv" in normalized):
        return "snowy-rainy"
    if "nieve" in normalized or "nevadas" in normalized:
        return "snowy"
    if "granizo" in normalized:
        return "hail"
    if "niebla" in normalized or "bruma" in normalized:
        return "fog"
    if "lluv" in normalized or "chubasc" in normalized:
        return "pouring" if "fuerte" in normalized or "intensa" in normalized else "rainy"
    if "despejado" in normalized:
        return "clear-night" if (element.text or "").strip().endswith("n") else "sunny"
    if "poco nuboso" in normalized or "intervalos nubosos" in normalized:
        return "partlycloudy"
    if "nuboso" in normalized or "cubierto" in normalized:
        return "cloudy"
    return None


def _local_hour(day: date, hour: int, zone: ZoneInfo, fold: int = 0) -> datetime | None:
    local = datetime.combine(day, time.min, zone) + timedelta(hours=hour)
    local = local.replace(fold=min(fold, 1))
    utc = local.astimezone(UTC)
    if utc.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
        return None  # A clock hour skipped when daylight saving time begins.
    return utc


def parse_hourly_forecast(xml: str | bytes, city_id: str, zone: ZoneInfo) -> HourlyForecasts:
    """Read hourly values and keep six-hour rain probabilities as intervals."""
    root = _root(xml)
    _city(root, city_id)
    issued_at = _issued(root, zone)
    hours: list[HourlyForecast] = []
    windows: list[ProbabilityWindow] = []
    fields = {
        "estado_cielo", "temperatura", "sens_termica", "humedad_relativa",
        "precipitacion", "nieve", "viento", "racha_max",
    }
    for day_element in root.findall("./prediccion/dia"):
        day = _day(day_element.get("fecha"))
        data: dict[tuple[int, int], dict[str, ET.Element]] = defaultdict(dict)
        ordinal: dict[tuple[str, str], int] = defaultdict(int)
        for element in day_element:
            period = element.get("periodo", "")
            if element.tag == "prob_precipitacion" and _WINDOW.fullmatch(period):
                start_hour, end_hour = int(period[:2]), int(period[2:])
                probability = _integer(element.text)
                if probability is not None and start_hour <= 23 and end_hour <= 24:
                    start = _local_hour(day, start_hour, zone)
                    end_day = day + timedelta(days=int(end_hour <= start_hour))
                    end = _local_hour(end_day, end_hour, zone)
                    if start is not None and end is not None:
                        windows.append(ProbabilityWindow(start, end, probability))
                continue
            if element.tag not in fields or not _HOUR.fullmatch(period):
                continue
            hour = int(period)
            if hour > 24:
                continue
            index = ordinal[(element.tag, period)]
            ordinal[(element.tag, period)] += 1
            data[(hour, index)][element.tag] = element

        for (hour, index), values in data.items():
            when = _local_hour(day, hour, zone, index)
            if when is None:
                continue
            wind_element = values.get("viento")
            wind_direction, wind_bearing = _direction(
                wind_element.findtext("direccion") if wind_element is not None else None
            )
            hours.append(HourlyForecast(
                time=when,
                condition=_condition(values.get("estado_cielo")),
                temperature=_number(values["temperatura"].text) if "temperatura" in values else None,
                apparent_temperature=_number(values["sens_termica"].text) if "sens_termica" in values else None,
                humidity=_number(values["humedad_relativa"].text) if "humedad_relativa" in values else None,
                precipitation=_number(values["precipitacion"].text) if "precipitacion" in values else None,
                snow=_number(values["nieve"].text) if "nieve" in values else None,
                wind_speed=_number(wind_element.findtext("velocidad")) if wind_element is not None else None,
                wind_direction=wind_direction,
                wind_bearing=wind_bearing,
                gust_speed=_number(values["racha_max"].text) if "racha_max" in values else None,
            ))
    if not hours:
        raise AemetFormatError("No hourly forecast")
    hours.sort(key=lambda item: item.time)
    windows.sort(key=lambda item: item.start)
    return HourlyForecasts(city_id, _text(root.findtext("nombre")) or city_id, issued_at, tuple(hours), tuple(windows))


def _preferred(day: ET.Element, tag: str) -> ET.Element | None:
    for period in ("00-24", None):
        for element in day.findall(tag):
            if element.get("periodo") != period:
                continue
            if (element.text or "").strip() or element.get("descripcion", "").strip():
                return element
            if any((child.text or "").strip() for child in element.iter() if child is not element):
                return element
    return None


def parse_daily_forecast(xml: str | bytes, city_id: str, zone: ZoneInfo) -> DailyForecasts:
    """Read the seven-day municipal forecast."""
    root = _root(xml)
    _city(root, city_id)
    issued_at = _issued(root, zone)
    days: list[DailyForecast] = []
    for item in root.findall("./prediccion/dia"):
        wind = _preferred(item, "viento")
        wind_direction, wind_bearing = _direction(wind.findtext("direccion") if wind is not None else None)
        temperature = item.find("temperatura")
        apparent = item.find("sens_termica")
        humidity = item.find("humedad_relativa")
        days.append(DailyForecast(
            date=_day(item.get("fecha")),
            condition=_condition(_preferred(item, "estado_cielo")),
            maximum_temperature=_number(temperature.findtext("maxima")) if temperature is not None else None,
            minimum_temperature=_number(temperature.findtext("minima")) if temperature is not None else None,
            maximum_apparent_temperature=_number(apparent.findtext("maxima")) if apparent is not None else None,
            minimum_apparent_temperature=_number(apparent.findtext("minima")) if apparent is not None else None,
            maximum_humidity=_number(humidity.findtext("maxima")) if humidity is not None else None,
            minimum_humidity=_number(humidity.findtext("minima")) if humidity is not None else None,
            precipitation_probability=_integer(_preferred(item, "prob_precipitacion").text)
            if _preferred(item, "prob_precipitacion") is not None else None,
            snow_line=_number(_preferred(item, "cota_nieve_prov").text)
            if _preferred(item, "cota_nieve_prov") is not None else None,
            wind_speed=_number(wind.findtext("velocidad")) if wind is not None else None,
            wind_direction=wind_direction,
            wind_bearing=wind_bearing,
            gust_speed=_number(_preferred(item, "racha_max").text)
            if _preferred(item, "racha_max") is not None else None,
            uv_index=_number(item.findtext("uv_max")),
        ))
    if not days:
        raise AemetFormatError("No daily forecast")
    days.sort(key=lambda item: item.date)
    return DailyForecasts(city_id, _text(root.findtext("nombre")) or city_id, issued_at, tuple(days))


def parse_warnings(xml: str | bytes, zone_id: str) -> Warnings:
    """Read active warning links; the first RSS item is an aggregate archive."""
    root = _root(xml)
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise AemetFormatError("Invalid warning feed")
    items = channel.findall("item")
    if items and (items[0].findtext("title") or "").startswith("Estado completo de avisos"):
        items = items[1:]
    warnings: list[Warning] = []
    for item in items:
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        parsed = urlparse(url)
        if title and parsed.scheme == "https" and parsed.hostname in ("www.aemet.es", "aemet.es"):
            warnings.append(Warning(title, url))
    published = (channel.findtext("lastBuildDate") or channel.findtext("pubDate") or "").strip()
    try:
        published_at = datetime.fromisoformat(published).astimezone(UTC) if published else None
    except ValueError as err:
        raise AemetFormatError("Invalid warning issue time") from err
    name = _text(channel.findtext("title") or zone_id).strip()
    return Warnings(zone_id, name, published_at, tuple(warnings))
