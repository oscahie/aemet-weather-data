"""Parser regressions for missing values, identity, intervals, and DST."""

from datetime import UTC, date, datetime
from pathlib import Path
import sys
import types
import unittest
from zoneinfo import ZoneInfo


# The parser is standard-library-only; do not import Home Assistant in these tests.
package = types.ModuleType("aemet_public")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/aemet_public")]
sys.modules.setdefault("aemet_public", package)

from aemet_public.parsers import (  # noqa: E402
    AemetFormatError,
    parse_daily_forecast,
    parse_daily_observations,
    parse_hourly_forecast,
    parse_observations,
    parse_today,
    parse_warnings,
)


MADRID = ZoneInfo("Europe/Madrid")


class ObservationTests(unittest.TestCase):
    def test_hourly_values_and_missing_are_distinct(self) -> None:
        xml = """<root><elaborado utc="2026-11-01T00:40:00"/>
          <estacion id_s="9263D" id_c="9263D" nombre="Pamplona, Aeropuerto">
            <periodo utc="2026-10-31T23:00:00"><temperatura>6.9</temperatura>
              <dir_viento>O</dir_viento><precipitacion>0.0</precipitacion></periodo>
            <periodo utc="2026-11-01T00:00:00"><temperatura>6.4</temperatura>
              <precipitacion/><dir_viento>c</dir_viento></periodo>
          </estacion></root>"""
        result = parse_observations(xml, "9263D")
        self.assertEqual(result.readings[0].precipitation, 0)
        self.assertEqual(result.readings[0].wind_bearing, 270)
        self.assertIsNone(result.latest.precipitation)
        self.assertIsNone(result.latest.wind_bearing)
        self.assertEqual(result.latest.time, datetime(2026, 11, 1, tzinfo=UTC))
        with self.assertRaises(AemetFormatError):
            parse_observations(xml, "9999X")

    def test_today_and_completed_days_use_id_c(self) -> None:
        today = """<root><elaborado utc="2026-10-31T23:44:14"/>
          <estacion id_s="08085" id_c="9263D" nombre="Pamplona, Aeropuerto">
            <tmax>6.9</tmax><tmin>6.6</tmin><pre_0024>0.0</pre_0024>
          </estacion></root>"""
        result = parse_today(today, "9263D", date(2026, 11, 1))
        self.assertEqual(result.summary.maximum_temperature, 6.9)
        self.assertEqual(result.summary.precipitation, 0)
        daily = """<root><elaborado utc="2026-10-31T23:44:14"/>
          <estacion id_s="08085" id_c="9263D" nombre="Pamplona, Aeropuerto">
            <periodo local="2026-10-30T00:00:00"><tmax>21.0</tmax>
              <pre_0024>0.0</pre_0024><pre_0612/></periodo>
          </estacion></root>"""
        summary = parse_daily_observations(daily, "9263D").latest
        self.assertEqual(summary.date, date(2026, 10, 30))
        self.assertEqual(summary.maximum_temperature, 21)
        self.assertIsNone(summary.precipitation_06_12)


class ForecastTests(unittest.TestCase):
    def test_hourly_probability_window_crosses_midnight(self) -> None:
        xml = """<root id="31201"><elaborado>2026-10-31T20:59:07</elaborado>
          <nombre>Pamplona/Iruña</nombre><prediccion><dia fecha="2026-10-31">
            <estado_cielo periodo="23" descripcion="Despejado">11n</estado_cielo>
            <temperatura periodo="23">8</temperatura>
            <precipitacion periodo="23">0</precipitacion>
            <prob_precipitacion periodo="1901">30</prob_precipitacion>
          </dia></prediccion></root>"""
        result = parse_hourly_forecast(xml, "31201", MADRID)
        self.assertEqual(result.hours[0].condition, "clear-night")
        self.assertEqual(result.hours[0].precipitation, 0)
        window = result.probability_windows[0]
        self.assertEqual(window.start.astimezone(MADRID).hour, 19)
        self.assertEqual(window.end.astimezone(MADRID).date(), date(2026, 11, 1))
        self.assertEqual(window.end.astimezone(MADRID).hour, 1)

    def test_repeated_dst_hour_gets_distinct_utc_times(self) -> None:
        xml = """<root id="31201"><elaborado>2026-10-24T20:00:00</elaborado>
          <prediccion><dia fecha="2026-10-25">
            <temperatura periodo="02">12</temperatura>
            <temperatura periodo="02">11</temperatura>
          </dia></prediccion></root>"""
        result = parse_hourly_forecast(xml, "31201", MADRID)
        self.assertEqual(len(result.hours), 2)
        self.assertEqual(result.hours[0].time, datetime(2026, 10, 25, 0, tzinfo=UTC))
        self.assertEqual(result.hours[1].time, datetime(2026, 10, 25, 1, tzinfo=UTC))

    def test_daily_forecast_does_not_use_partial_period_as_whole_day(self) -> None:
        xml = """<root id="31201"><elaborado>2026-10-31T20:59:07</elaborado>
          <prediccion><dia fecha="2026-11-01">
            <prob_precipitacion periodo="00-24"/>
            <prob_precipitacion periodo="18-24">80</prob_precipitacion>
            <estado_cielo periodo="00-24" descripcion="Nuboso">14</estado_cielo>
            <temperatura><maxima>16</maxima><minima>7</minima></temperatura>
            <uv_max>3</uv_max>
          </dia></prediccion></root>"""
        day = parse_daily_forecast(xml, "31201", MADRID).days[0]
        self.assertIsNone(day.precipitation_probability)
        self.assertEqual(day.condition, "cloudy")
        self.assertEqual(day.maximum_temperature, 16)
        self.assertEqual(day.uv_index, 3)


class WarningTests(unittest.TestCase):
    def test_aggregate_item_is_not_an_active_warning(self) -> None:
        xml = """<rss><channel><title>AEMET - Centro de Navarra</title>
          <lastBuildDate>2026-10-31T22:50:02+00:00</lastBuildDate>
          <item><title>Estado completo de avisos para Centro de Navarra</title>
            <link>https://www.aemet.es/archive.tar.gz</link></item>
          <item><title>Aviso amarillo por viento</title>
            <link>https://www.aemet.es/cap/wind.xml</link></item>
          </channel></rss>"""
        result = parse_warnings(xml, "743102")
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].title, "Aviso amarillo por viento")


class SavedAemetDocumentTests(unittest.TestCase):
    """Exercise the exact XML documents served for Pamplona during development."""

    def test_saved_public_documents(self) -> None:
        folder = Path(__file__).parent
        observations = parse_observations(
            (folder / "fixtures_observation.xml").read_bytes(), "9263D"
        )
        today = parse_today(
            (folder / "fixtures_today.xml").read_bytes(), "9263D", date(2026, 11, 1)
        )
        past = parse_daily_observations(
            (folder / "fixtures_daily.xml").read_bytes(), "9263D"
        )
        hourly = parse_hourly_forecast(
            (folder / "fixtures_hourly_forecast.xml").read_bytes(), "31201", MADRID
        )
        daily = parse_daily_forecast(
            (folder / "fixtures_daily_forecast.xml").read_bytes(), "31201", MADRID
        )
        warnings = parse_warnings(
            (folder / "fixtures_warnings.xml").read_bytes(), "743102"
        )
        self.assertEqual(len(observations.readings), 24)
        self.assertEqual(observations.latest.temperature, 6.9)
        self.assertEqual(today.summary.minimum_temperature, 6.6)
        self.assertEqual(past.latest.precipitation, 4.3)
        self.assertEqual(len(hourly.hours), 48)
        self.assertEqual(len(hourly.probability_windows), 8)
        self.assertEqual(sum(hour.condition == "partlycloudy" for hour in hourly.hours), 14)
        self.assertNotIn(None, (hour.condition for hour in hourly.hours))
        self.assertEqual(len(daily.days), 7)
        self.assertEqual(daily.days[1].minimum_humidity, 55)
        self.assertEqual(len(warnings.items), 0)


if __name__ == "__main__":
    unittest.main()
