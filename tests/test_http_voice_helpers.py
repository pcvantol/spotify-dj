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

    class Response:
        def __init__(self, *, status=200, text=None, body=None, content_type=None, headers=None):
            self.status = status
            self.text = text
            self.body = body
            self.content_type = content_type
            self.headers = headers or {}

    http.HomeAssistantView = HomeAssistantView
    core.HomeAssistant = object
    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.web = types.SimpleNamespace(Response=Response)
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

    def test_command_failed_text_uses_device_language(self) -> None:
        nl_runtime = types.SimpleNamespace(device_language=lambda: "nl")
        en_runtime = types.SimpleNamespace(device_language=lambda: "en")
        unknown_runtime = types.SimpleNamespace()

        self.assertIn(
            "Spotify niet starten",
            self.http._command_failed_text(
                nl_runtime,
                RuntimeError("Spotify playback device unavailable"),
            ),
        )
        self.assertIn(
            "could not start Spotify playback",
            self.http._command_failed_text(
                en_runtime,
                RuntimeError("media_player.play_media failed"),
            ),
        )
        self.assertIn(
            "Assist pipeline",
            self.http._command_failed_text(
                en_runtime,
                RuntimeError("HA Assist pipeline failed"),
            ),
        )
        self.assertIn(
            "something went wrong",
            self.http._command_failed_text(unknown_runtime),
        )

    def test_voice_view_sends_friendly_dj_response_on_command_failure(self) -> None:
        const = importlib.import_module("custom_components.spotify_dj.const")

        class Runtime:
            config = {}

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def device_language(self):
                return "nl"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()
        hass = types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})
        sent_responses = []

        async def fail_command(hass, runtime, user_text, play=True):
            raise RuntimeError("Spotify playback device unavailable")

        async def send_failure(hass, runtime, exc=None):
            runtime.update(last_error="ESP DJ response failed")
            sent_responses.append(self.http._command_failed_text(runtime, exc))
            return {"success": True, "spoken": False}

        original_command = self.http.process_text_command
        original_failure = self.http._send_failure_dj_response
        self.http.process_text_command = fail_command
        self.http._send_failure_dj_response = send_failure

        class Request:
            headers = {"X-SpotifyDJ-Text": "Play Pearl Jam"}
            app = {"hass": hass}

            async def read(self):
                return b""

        try:
            response = asyncio.run(self.http.SpotifyDJVoiceView(None).post(Request()))
        finally:
            self.http.process_text_command = original_command
            self.http._send_failure_dj_response = original_failure

        self.assertEqual(response["status_code"], 500)
        self.assertEqual(response["payload"]["error"], "command_failed")
        self.assertIn("Spotify niet starten", response["payload"]["dj_text"])
        self.assertEqual(response["payload"]["dj_response"], {"success": True, "spoken": False})
        self.assertEqual(sent_responses, [response["payload"]["dj_text"]])
        self.assertEqual(runtime.last_update["last_error"], "Spotify playback device unavailable")

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
        self.assertEqual(response["payload"]["error"], "invalid_pair_code")
        self.assertIn("does not match", response["payload"]["message"])

    def test_pair_view_includes_spotify_refresh_token_aliases(self) -> None:
        const = importlib.import_module("custom_components.spotify_dj.const")

        class Runtime:
            config = {const.CONF_PAIR_CODE: "123456"}
            device_status = {}

            def ensure_device_token(self):
                self.device_token = "device-token"
                return self.device_token

            def mqtt_payload(self):
                return {"host": "mqtt.local"}

            def spotify_payload(self):
                return {
                    "client_id": "client-id",
                    "refresh_token": "refresh-token",
                    "spotify_client_id": "client-id",
                    "spotify_refresh_token": "refresh-token",
                    "market": "NL",
                    "scopes": ["scope-a"],
                }

            def device_language(self):
                return "nl"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        class Request:
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {
                    "device_id": "spotifydj-device",
                    "pair_code": "123456",
                    "local_url": "http://spotifydj.local",
                }

        response = asyncio.run(self.http.SpotifyDJPairView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        spotify = response["payload"]["spotify"]
        self.assertEqual(spotify["refresh_token"], "refresh-token")
        self.assertEqual(spotify["spotify_refresh_token"], "refresh-token")
        self.assertEqual(response["payload"]["refresh_token"], "refresh-token")
        self.assertEqual(response["payload"]["spotify_refresh_token"], "refresh-token")
        self.assertEqual(response["payload"]["mqtt"]["host"], "mqtt.local")
        self.assertEqual(response["payload"]["device_language"], "nl")
        self.assertEqual(response["payload"]["language"], "nl")

    def test_status_view_includes_spotify_refresh_token_aliases(self) -> None:
        const = importlib.import_module("custom_components.spotify_dj.const")

        class Runtime:
            device_token = "device-token"
            device_status = {}
            ota_in_progress = False
            ota_last_error = None
            config = {
                const.CONF_ASSIST_PIPELINE_ID: "pipeline",
                const.CONF_HA_EXTERNAL_URL: "https://ha.example",
            }

            def authorize_device_request(self, headers, body_device_id=None):
                return True

            def mqtt_payload(self):
                return {"host": "mqtt.local"}

            def spotify_payload(self):
                return {
                    "client_id": "client-id",
                    "refresh_token": "refresh-token",
                    "spotify_client_id": "client-id",
                    "spotify_refresh_token": "refresh-token",
                }

            def device_language(self):
                return "en"

            def update(self, **kwargs):
                self.last_update = kwargs

        runtime = Runtime()

        class Request:
            headers = {"Authorization": "Bearer device-token"}
            app = {"hass": types.SimpleNamespace(data={const.DOMAIN: {"runtime": runtime}})}

            async def json(self):
                return {"device_id": "spotifydj-device"}

        response = asyncio.run(self.http.SpotifyDJStatusView(None).post(Request()))

        self.assertEqual(response["status_code"], 200)
        self.assertEqual(response["payload"]["refresh_token"], "refresh-token")
        self.assertEqual(response["payload"]["spotify_refresh_token"], "refresh-token")
        self.assertEqual(response["payload"]["spotify"]["refresh_token"], "refresh-token")

    def test_tts_view_returns_wav_audio_for_valid_token(self) -> None:
        const = importlib.import_module("custom_components.spotify_dj.const")
        dj_response = importlib.import_module("custom_components.spotify_dj.dj_response")
        hass = types.SimpleNamespace(data={})
        token = dj_response.store_tts_audio(hass, b"RIFFxxxxWAVEdata", 120)
        request = types.SimpleNamespace(app={"hass": hass})

        response = asyncio.run(self.http.SpotifyDJTtsView(None).get(request, token))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "audio/wav")
        self.assertEqual(response.body, b"RIFFxxxxWAVEdata")
        self.assertEqual(response.headers["Content-Length"], "16")
        self.assertIn("tts_audio", hass.data[const.DOMAIN])

    def test_tts_view_returns_410_for_expired_token(self) -> None:
        dj_response = importlib.import_module("custom_components.spotify_dj.dj_response")
        hass = types.SimpleNamespace(data={})
        token = dj_response.store_tts_audio(hass, b"RIFFxxxxWAVEdata", 120)
        dj_response._store(hass)[token].expires_at = 0
        request = types.SimpleNamespace(app={"hass": hass})

        response = asyncio.run(self.http.SpotifyDJTtsView(None).get(request, token))

        self.assertEqual(response.status, 410)

    def test_tts_view_returns_404_for_unknown_token(self) -> None:
        request = types.SimpleNamespace(app={"hass": types.SimpleNamespace(data={})})

        response = asyncio.run(self.http.SpotifyDJTtsView(None).get(request, "unknown"))

        self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()
