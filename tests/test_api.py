"""Regression tests for streaming AEMET XML responses."""

import sys
import types
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch


package = types.ModuleType("aemet_weather_data")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/aemet_weather_data")]
sys.modules.setdefault("aemet_weather_data", package)

try:
    import aiohttp  # noqa: F401
except ImportError:
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.ClientError = type("ClientError", (Exception,), {})
    aiohttp.ClientSession = type("ClientSession", (), {})
    sys.modules["aiohttp"] = aiohttp

from aemet_weather_data.api import AemetError, AemetWeatherDataClient  # noqa: E402


class ChunkedContent:
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self.chunks = chunks

    async def iter_chunked(self, size: int):
        for chunk in self.chunks:
            yield chunk


class Response:
    status = 200
    url = types.SimpleNamespace(host="www.aemet.es")

    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self.content = ChunkedContent(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def raise_for_status(self) -> None:
        pass


class Session:
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self.response = Response(chunks)

    def get(self, *args, **kwargs):
        return self.response


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_every_response_chunk(self) -> None:
        client = AemetWeatherDataClient(
            Session((b"<root>", b"<value>1</value>", b"</root>")),
            ZoneInfo("Europe/Madrid"),
        )
        self.assertEqual(
            await client._xml("/xml/municipios/localidad_31201.xml"),
            b"<root><value>1</value></root>",
        )

    async def test_rejects_oversized_response(self) -> None:
        client = AemetWeatherDataClient(Session((b"abc", b"def")), ZoneInfo("Europe/Madrid"))
        with patch("aemet_weather_data.api.MAX_RESPONSE_BYTES", 5):
            with self.assertRaises(AemetError):
                await client._xml("/test.xml")
