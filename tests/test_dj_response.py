from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_stubs() -> None:
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    core = sys.modules.setdefault(
        "homeassistant.core",
        types.ModuleType("homeassistant.core"),
    )
    helpers = sys.modules.setdefault(
        "homeassistant.helpers",
        types.ModuleType("homeassistant.helpers"),
    )
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    aiohttp.ClientTimeout = ClientTimeout
    core.HomeAssistant = object
    aiohttp_client.async_get_clientsession = lambda hass: None
    helpers.aiohttp_client = aiohttp_client


class FakeResponse:
    def __init__(self, status: int, payload: dict | None = None, text: str = "") -> None:
        self.status = status
        self.payload = payload or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def text(self):
        return self._text

    async def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


class Runtime:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.updated = {}

    async def async_device_local_url(self, hass):
        return "http://spotifydj.local"

    def device_headers(self):
        return {"Authorization": "Bearer token", "Content-Type": "application/json"}

    def update(self, **kwargs):
        self.updated.update(kwargs)


class DjResponseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_stubs()
        cls.const = importlib.import_module("custom_components.spotify_dj.const")
        cls.dj_response = importlib.import_module("custom_components.spotify_dj.dj_response")

    def tearDown(self) -> None:
        self.dj_response.create_tts_wav = lambda hass, text, conf: None

    def test_send_dj_response_with_successful_pcm_wav_url(self) -> None:
        hass = types.SimpleNamespace(data={})
        runtime = Runtime({self.const.CONF_HA_EXTERNAL_URL: "http://ha.local:8123"})
        session = FakeSession(FakeResponse(200, {"success": True, "spoken": True, "displayed": True}))

        async def create_wav(hass, text, conf):
            return b"RIFFxxxxWAVEdata"

        self.dj_response.create_tts_wav = create_wav
        self.dj_response.async_get_clientsession = lambda hass: session

        result = asyncio.run(
            self.dj_response.async_send_dj_response(hass, runtime, "Daar gaan we")
        )

        payload = session.calls[0]["json"]
        self.assertEqual(session.calls[0]["url"], "http://spotifydj.local/api/device/dj_response")
        self.assertEqual(payload["text"], "Daar gaan we")
        self.assertIn("/api/spotify_dj/tts/", payload["audio_url"])
        self.assertTrue(result["spoken"])
        self.assertTrue(runtime.updated["last_dj_spoken"])

    def test_tts_failure_sends_text_only_payload(self) -> None:
        hass = types.SimpleNamespace(data={})
        runtime = Runtime({self.const.CONF_HA_EXTERNAL_URL: "http://ha.local:8123"})
        session = FakeSession(FakeResponse(200, {"success": True, "spoken": False, "displayed": True}))

        async def fail_tts(hass, text, conf):
            raise RuntimeError("tts failed")

        self.dj_response.create_tts_wav = fail_tts
        self.dj_response.async_get_clientsession = lambda hass: session

        result = asyncio.run(
            self.dj_response.async_send_dj_response(hass, runtime, "Tekst alleen")
        )

        payload = session.calls[0]["json"]
        self.assertEqual(payload, {"text": "Tekst alleen"})
        self.assertFalse(result["spoken"])
        self.assertTrue(result["displayed"])

    def test_non_wav_tts_sends_text_only_payload(self) -> None:
        hass = types.SimpleNamespace(data={})
        runtime = Runtime({self.const.CONF_HA_EXTERNAL_URL: "http://ha.local:8123"})
        session = FakeSession(FakeResponse(200, {"success": True, "spoken": False, "displayed": True}))

        async def create_mp3(hass, text, conf):
            return b"ID3 mp3 data"

        self.dj_response.create_tts_wav = create_mp3
        self.dj_response.async_get_clientsession = lambda hass: session

        asyncio.run(self.dj_response.async_send_dj_response(hass, runtime, "Tekst"))

        self.assertEqual(session.calls[0]["json"], {"text": "Tekst"})

    def test_http_failure_raises_and_best_effort_reports_error(self) -> None:
        hass = types.SimpleNamespace(data={})
        runtime = Runtime({self.const.CONF_HA_EXTERNAL_URL: "http://ha.local:8123"})
        session = FakeSession(FakeResponse(500, text="boom"))

        async def fail_tts(hass, text, conf):
            raise RuntimeError("tts failed")

        self.dj_response.create_tts_wav = fail_tts
        self.dj_response.async_get_clientsession = lambda hass: session

        result = asyncio.run(
            self.dj_response.async_send_dj_response_best_effort(
                hass,
                runtime,
                "Tekst",
            )
        )

        self.assertFalse(result["success"])
        self.assertIn("HTTP 500", result["message"])
        self.assertIn("HTTP 500", runtime.updated["last_error"])


if __name__ == "__main__":
    unittest.main()
