from __future__ import annotations

import importlib
import asyncio
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_http_stubs() -> None:
    if "homeassistant.components.http" in sys.modules:
        return

    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    aiohttp.web = types.SimpleNamespace(Response=object)

    homeassistant = sys.modules.setdefault(
        "homeassistant", types.ModuleType("homeassistant")
    )
    components = types.ModuleType("homeassistant.components")
    http = types.ModuleType("homeassistant.components.http")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

    class HomeAssistantView:
        def json(self, payload, status_code=200):
            return {"payload": payload, "status_code": status_code}

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    http.HomeAssistantView = HomeAssistantView
    core.HomeAssistant = object
    aiohttp.ClientTimeout = ClientTimeout
    aiohttp_client.async_get_clientsession = lambda hass: None

    homeassistant.components = components
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.http"] = http
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    package = types.ModuleType("custom_components.spotify_dj")
    package.__path__ = [str(ROOT / "custom_components" / "spotify_dj")]
    sys.modules.setdefault("custom_components.spotify_dj", package)


class VoiceHttpHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_http_stubs()
        cls.http = importlib.import_module("custom_components.spotify_dj.http")

    def test_text_from_header_takes_precedence(self) -> None:
        text = self.http._text_from_payload(
            {"X-SpotifyDJ-Text": " Speel Pearl Jam "},
            {"text": "Speel Nirvana"},
        )

        self.assertEqual(text, "Speel Pearl Jam")

    def test_text_from_json_payload(self) -> None:
        text = self.http._text_from_payload({}, {"text": " Speel Nirvana "})

        self.assertEqual(text, "Speel Nirvana")

    def test_missing_text_response_documents_assist_flow(self) -> None:
        response = self.http._missing_text_response(self.http.SpotifyDJVoiceView(None))

        self.assertEqual(response["status_code"], 400)
        self.assertEqual(response["payload"]["error"], "missing_text")
        self.assertIn("X-SpotifyDJ-Text", response["payload"]["message"])
        self.assertIn("HA Assist pipeline", response["payload"]["message"])

    def test_pair_view_rejects_wrong_pair_code(self) -> None:
        const = importlib.import_module("custom_components.spotify_dj.const")

        class Runtime:
            config = {const.CONF_PAIR_CODE: "123456"}

            def update(self, **kwargs):
                self.last_update = kwargs

        class Request:
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": Runtime()}})}

            async def json(self):
                return {"device_id": "spotifydj-device", "pair_code": "654321"}

        response = asyncio.run(self.http.SpotifyDJPairView(None).post(Request()))

        self.assertEqual(response["status_code"], 401)
        self.assertEqual(response["payload"]["error"], "Invalid pairing code")


if __name__ == "__main__":
    unittest.main()
