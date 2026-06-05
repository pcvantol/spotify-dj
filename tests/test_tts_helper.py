from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_integration_stubs() -> None:
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    config_entries = sys.modules.setdefault(
        "homeassistant.config_entries",
        types.ModuleType("homeassistant.config_entries"),
    )
    core = sys.modules.setdefault(
        "homeassistant.core",
        types.ModuleType("homeassistant.core"),
    )
    helpers = sys.modules.setdefault(
        "homeassistant.helpers",
        types.ModuleType("homeassistant.helpers"),
    )
    components = sys.modules.setdefault(
        "homeassistant.components",
        types.ModuleType("homeassistant.components"),
    )
    http = sys.modules.setdefault(
        "homeassistant.components.http",
        types.ModuleType("homeassistant.components.http"),
    )
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )
    issue_registry = sys.modules.setdefault(
        "homeassistant.helpers.issue_registry",
        types.ModuleType("homeassistant.helpers.issue_registry"),
    )
    typing = sys.modules.setdefault(
        "homeassistant.helpers.typing",
        types.ModuleType("homeassistant.helpers.typing"),
    )

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class HomeAssistantView:
        def json(self, payload, status_code=200):
            return {"payload": payload, "status_code": status_code}

    class Response:
        def __init__(self, *, status=200, text=None, body=None, content_type=None, headers=None):
            self.status = status
            self.text = text
            self.body = body
            self.content_type = content_type
            self.headers = headers or {}

    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.web = getattr(aiohttp, "web", types.SimpleNamespace())
    config_entries.ConfigEntry = object
    core.HomeAssistant = object
    core.ServiceCall = object
    http.HomeAssistantView = HomeAssistantView
    aiohttp_client.async_get_clientsession = lambda hass: None
    issue_registry.IssueSeverity = types.SimpleNamespace(WARNING="warning")
    issue_registry.async_create_issue = lambda *args, **kwargs: None
    helpers.issue_registry = issue_registry
    typing.ConfigType = dict
    aiohttp.web = types.SimpleNamespace(Response=Response)
    sys.modules["homeassistant"].components = components


class TtsHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_integration_stubs()
        sys.modules.pop("custom_components.spotify_dj", None)
        cls.integration = importlib.import_module("custom_components.spotify_dj")
        cls.const = importlib.import_module("custom_components.spotify_dj.const")
        cls.dj_response = importlib.import_module("custom_components.spotify_dj.dj_response")

    def test_mqtt_payload_is_empty_without_host(self) -> None:
        entry = types.SimpleNamespace(data={}, options={})
        runtime = self.integration.SpotifyDJRuntime(entry=entry)

        self.assertEqual(runtime.mqtt_payload(), {})

    def test_mqtt_payload_contains_configured_broker(self) -> None:
        entry = types.SimpleNamespace(
            data={
                self.const.CONF_MQTT_HOST: "mqtt.local",
                self.const.CONF_MQTT_PORT: 1884,
                self.const.CONF_MQTT_USERNAME: "spotifydj",
                self.const.CONF_MQTT_PASSWORD: "secret",
            },
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)

        self.assertEqual(
            runtime.mqtt_payload(),
            {
                "host": "mqtt.local",
                "port": 1884,
                "username": "spotifydj",
                "password": "secret",
            },
        )

    def test_spotify_payload_contains_refresh_token_aliases(self) -> None:
        entry = types.SimpleNamespace(
            data={
                self.const.CONF_SPOTIFY_CLIENT_ID: "client-id",
                self.const.CONF_SPOTIFY_REFRESH_TOKEN: "refresh-token",
                self.const.CONF_SPOTIFY_MARKET: "NL",
                self.const.CONF_SPOTIFY_SCOPES: "scope-a scope-b",
            },
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)

        payload = runtime.spotify_payload()

        self.assertEqual(payload["client_id"], "client-id")
        self.assertEqual(payload["refresh_token"], "refresh-token")
        self.assertEqual(payload["spotify_client_id"], "client-id")
        self.assertEqual(payload["spotify_refresh_token"], "refresh-token")
        self.assertEqual(payload["market"], "NL")
        self.assertEqual(payload["scopes"], ["scope-a", "scope-b"])

    def test_pair_device_payload_includes_spotify_credentials_when_available(self) -> None:
        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def text(self):
                return '{"success": true}'

        class Session:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append({"url": url, **kwargs})
                return Response()

        entry = types.SimpleNamespace(
            data={
                self.const.CONF_DEVICE_ID: "spotifydj-123456",
                self.const.CONF_PAIR_CODE: "123456",
                self.const.CONF_DEVICE_LANGUAGE: "nl",
                self.const.CONF_SPOTIFY_CLIENT_ID: "client-id",
                self.const.CONF_SPOTIFY_REFRESH_TOKEN: "refresh-token",
            },
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)
        runtime.device_status["local_url"] = "http://spotifydj.local"
        session = Session()
        original_session = self.integration.async_get_clientsession
        self.integration.async_get_clientsession = lambda hass: session
        try:
            result = asyncio.run(runtime.pair_device(object()))
        finally:
            self.integration.async_get_clientsession = original_session

        self.assertTrue(result["success"])
        payload = session.calls[0]["json"]
        self.assertEqual(payload["device_language"], "nl")
        self.assertEqual(payload["language"], "nl")
        self.assertEqual(payload["spotify"]["refresh_token"], "refresh-token")
        self.assertEqual(payload["spotify"]["spotify_refresh_token"], "refresh-token")
        self.assertEqual(payload["refresh_token"], "refresh-token")
        self.assertEqual(payload["spotify_refresh_token"], "refresh-token")

    def test_start_ota_payload_uses_manifest_device_target(self) -> None:
        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def text(self):
                return '{"success": true}'

        class Session:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append({"url": url, **kwargs})
                return Response()

        entry = types.SimpleNamespace(
            data={
                self.const.CONF_DEVICE_ID: "spotifydj-90B70990A994",
                self.const.CONF_DEVICE_TOKEN: "device-token",
            },
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)
        runtime.device_token = "device-token"
        runtime.device_status["local_url"] = "http://spotifydj-90B70990A994.local"
        release = types.SimpleNamespace(
            version="2.7.0",
            firmware_url="https://example/spotifydj-device-v2.7.0.bin",
            sha256="a" * 64,
            device="lilygo-t-embed-s3",
            firmware_asset="spotifydj-device-v2.7.0.bin",
        )
        session = Session()
        original_session = self.integration.async_get_clientsession
        self.integration.async_get_clientsession = lambda hass: session
        try:
            asyncio.run(runtime.start_ota(object(), release))
        finally:
            self.integration.async_get_clientsession = original_session

        call = session.calls[0]
        self.assertEqual(call["url"], "http://spotifydj-90B70990A994.local/api/device/ota")
        self.assertEqual(call["headers"]["Authorization"], "Bearer device-token")
        self.assertEqual(
            call["json"],
            {
                "version": "2.7.0",
                "url": "https://example/spotifydj-device-v2.7.0.bin",
                "sha256": "a" * 64,
                "device": "lilygo-t-embed-s3",
                "asset": "spotifydj-device-v2.7.0.bin",
            },
        )

    def test_start_ota_preserves_wrong_device_target_error(self) -> None:
        class Response:
            status = 400

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def text(self):
                return "Wrong device target"

        class Session:
            def post(self, url, **kwargs):
                return Response()

        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "spotifydj-90B70990A994"},
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)
        runtime.device_status["local_url"] = "http://spotifydj-90B70990A994.local"
        release = types.SimpleNamespace(
            version="2.7.0",
            firmware_url="https://example/spotifydj-device-v2.7.0.bin",
            sha256="a" * 64,
            device="spotifydj-device",
            firmware_asset="spotifydj-device-v2.7.0.bin",
        )
        original_session = self.integration.async_get_clientsession
        self.integration.async_get_clientsession = lambda hass: Session()
        try:
            with self.assertRaisesRegex(RuntimeError, "Wrong device target"):
                asyncio.run(runtime.start_ota(object(), release))
        finally:
            self.integration.async_get_clientsession = original_session

        self.assertIn("Wrong device target", runtime.ota_last_error)

    def test_url_from_service_info_matches_device_id(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "spotifydj-123456"},
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)
        info = types.SimpleNamespace(
            name="spotifydj-123456._spotifydj._tcp.local.",
            server="spotifydj-123456.local.",
            port=8080,
        )

        url = self.integration._url_from_service_info(info, runtime)

        self.assertEqual(url, "http://spotifydj-123456.local:8080")

    def test_url_from_service_info_matches_friendly_mdns_name(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "spotifydj-123456"},
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)
        info = types.SimpleNamespace(
            name="SpotifyDJ 123456._spotifydj._tcp.local.",
            server="spotifydj-123456.local.",
            port=80,
        )

        url = self.integration._url_from_service_info(info, runtime)

        self.assertEqual(url, "http://spotifydj-123456.local")

    def test_url_from_service_info_ignores_other_devices(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "spotifydj-123456"},
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)
        info = types.SimpleNamespace(
            name="spotifydj-other._spotifydj._tcp.local.",
            server="spotifydj-other.local.",
            port=80,
        )

        self.assertIsNone(self.integration._url_from_service_info(info, runtime))

    def test_mdns_service_name_candidates_include_device_and_friendly_names(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "spotifydj-123456"},
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)

        names = self.integration._mdns_service_name_candidates(runtime)

        self.assertIn("spotifydj-123456._spotifydj._tcp.local.", names)
        self.assertIn("SpotifyDJ 123456._spotifydj._tcp.local.", names)

    def test_device_local_url_falls_back_to_mdns_hostname(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "spotifydj-90B70990A994"},
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)

        url = asyncio.run(runtime.async_device_local_url(hass=object()))

        self.assertEqual(url, "http://spotifydj-90B70990A994.local")

    def test_device_local_url_does_not_fallback_to_pair_code_hostname(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "spotifydj-981032"},
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)

        url = asyncio.run(runtime.async_device_local_url(hass=object()))

        self.assertIsNone(url)

    def test_device_local_url_ignores_stored_pair_code_hostname(self) -> None:
        entry = types.SimpleNamespace(
            data={
                self.const.CONF_DEVICE_ID: "spotifydj-981032",
                self.const.CONF_LOCAL_URL: "http://spotifydj-981032.local",
            },
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)

        url = asyncio.run(runtime.async_device_local_url(hass=object()))

        self.assertIsNone(url)

    def test_device_local_url_uses_mdns_browse_for_pair_code_entry(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "spotifydj-981032"},
            options={},
        )
        runtime = self.integration.SpotifyDJRuntime(entry=entry)

        async def discover(hass, runtime):
            return "http://spotifydj-90B70990A994.local"

        original_discover = self.integration.async_discover_device_url
        self.integration.async_discover_device_url = discover
        try:
            url = asyncio.run(runtime.async_device_local_url(hass=object()))
        finally:
            self.integration.async_discover_device_url = original_discover

        self.assertEqual(url, "http://spotifydj-90B70990A994.local")

    def test_tts_audio_store_returns_wav_and_unknown_404(self) -> None:
        hass = types.SimpleNamespace(data={})

        token = self.dj_response.store_tts_audio(hass, b"RIFFxxxxWAVEdata", 120)

        status, audio = self.dj_response.get_tts_audio(hass, token)
        self.assertEqual(status, 200)
        self.assertEqual(audio, b"RIFFxxxxWAVEdata")
        status, audio = self.dj_response.get_tts_audio(hass, "missing")
        self.assertEqual(status, 404)
        self.assertIsNone(audio)

    def test_tts_audio_store_expired_returns_410(self) -> None:
        hass = types.SimpleNamespace(data={})

        token = self.dj_response.store_tts_audio(hass, b"RIFFxxxxWAVEdata", 1)
        self.dj_response._store(hass)[token].expires_at = 0

        status, audio = self.dj_response.get_tts_audio(hass, token)
        self.assertEqual(status, 410)
        self.assertIsNone(audio)


if __name__ == "__main__":
    unittest.main()
