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
    voluptuous = sys.modules.setdefault("voluptuous", types.ModuleType("voluptuous"))
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
    repairs = sys.modules.setdefault(
        "homeassistant.components.repairs",
        types.ModuleType("homeassistant.components.repairs"),
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

    class RepairsFlow:
        pass

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
    voluptuous.Schema = lambda schema: schema
    config_entries.ConfigEntry = object
    core.HomeAssistant = object
    core.Context = object
    core.ServiceCall = object
    http.HomeAssistantView = HomeAssistantView
    repairs.RepairsFlow = RepairsFlow
    aiohttp_client.async_get_clientsession = lambda hass: None
    issue_registry.IssueSeverity = types.SimpleNamespace(WARNING="warning")
    issue_registry.async_create_issue = lambda *args, **kwargs: None
    helpers.issue_registry = issue_registry
    typing.ConfigType = dict
    aiohttp.web = types.SimpleNamespace(Response=Response)
    sys.modules["homeassistant"].components = components
    components.repairs = repairs


class TtsHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_integration_stubs()
        sys.modules.pop("custom_components.djconnect", None)
        cls.integration = importlib.import_module("custom_components.djconnect")
        cls.const = importlib.import_module("custom_components.djconnect.const")
        cls.dj_response = importlib.import_module("custom_components.djconnect.dj_response")
        cls.http = importlib.import_module("custom_components.djconnect.http")

    def test_device_command_posts_to_local_command_api(self) -> None:
        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def text(self):
                return '{"success": true, "status": {"volume": 35}}'

        class Session:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append({"url": url, **kwargs})
                return Response()

        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "djconnect-lilygo-90B70990A994"},
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        runtime.device_token = "device-token"
        runtime.device_status["local_url"] = "http://djconnect.local"
        session = Session()
        original_session = self.integration.async_get_clientsession
        self.integration.async_get_clientsession = lambda hass: session
        try:
            result = asyncio.run(
                runtime.async_device_command(object(), "set_volume", value=35)
            )
        finally:
            self.integration.async_get_clientsession = original_session

        self.assertTrue(result["success"])
        self.assertEqual(
            session.calls[0]["url"],
            "http://djconnect.local/api/device/command",
        )
        self.assertEqual(session.calls[0]["headers"]["Authorization"], "Bearer device-token")
        self.assertEqual(
            session.calls[0]["json"],
            {"command": "set_volume", "value": 35},
        )
        self.assertEqual(runtime.device_status["volume"], 35)

    def test_service_text_accepts_ui_specific_aliases_and_legacy_text(self) -> None:
        self.assertEqual(
            self.integration._service_text(
                types.SimpleNamespace(data={"command_text": "Speel Pearl Jam"}),
                "default",
                "command_text",
            ),
            "Speel Pearl Jam",
        )
        self.assertEqual(
            self.integration._service_text(
                types.SimpleNamespace(data={"text": "Legacy Pearl Jam"}),
                "default",
                "command_text",
            ),
            "Legacy Pearl Jam",
        )
        self.assertEqual(
            self.integration._service_text(
                types.SimpleNamespace(data={"dj_response_text": "Daar gaan we"}),
                "default",
                "dj_response_text",
            ),
            "Daar gaan we",
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
        runtime = self.integration.DJConnectRuntime(entry=entry)

        payload = runtime.spotify_payload()

        self.assertEqual(payload["client_id"], "client-id")
        self.assertEqual(payload["refresh_token"], "refresh-token")
        self.assertEqual(payload["spotify_client_id"], "client-id")
        self.assertEqual(payload["spotify_refresh_token"], "refresh-token")
        self.assertEqual(payload["market"], "NL")
        self.assertEqual(payload["scopes"], ["scope-a", "scope-b"])

    def test_spotify_payload_uses_latest_rotated_refresh_token(self) -> None:
        entry = types.SimpleNamespace(
            data={
                self.const.CONF_SPOTIFY_CLIENT_ID: "client-id",
                self.const.CONF_SPOTIFY_REFRESH_TOKEN: "old-token",
                self.const.CONF_SPOTIFY_MARKET: "NL",
            },
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        runtime.latest_spotify_refresh_token = "new-token"

        payload = runtime.get_current_spotify_credentials()

        self.assertEqual(payload["refresh_token"], "new-token")
        self.assertEqual(payload["spotify_refresh_token"], "new-token")

    def test_restore_runtime_restores_persisted_pairing_identity(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                self.const.CONF_DEVICE_ID: "djconnect-lilygo-90B70990A994",
                self.const.CONF_PAIR_CODE: "981032",
                self.const.CONF_DEVICE_TOKEN: "device-token",
                self.const.CONF_LOCAL_URL: "http://djconnect-lilygo-90B70990A994.local",
            },
            options={},
        )
        hass = types.SimpleNamespace(data={self.const.DOMAIN: {}})

        runtime = self.integration._restore_runtime(hass, entry)

        self.assertEqual(runtime.device_token, "device-token")
        self.assertEqual(runtime.pairing_device_id, "djconnect-lilygo-90B70990A994")
        self.assertEqual(runtime.pairing_code, "981032")
        self.assertEqual(runtime.device_status["device_id"], "djconnect-lilygo-90B70990A994")
        self.assertEqual(
            runtime.device_status["local_url"],
            "http://djconnect-lilygo-90B70990A994.local",
        )

    def test_restore_runtime_ignores_obsolete_pair_code_local_url(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                self.const.CONF_DEVICE_ID: "djconnect-981032",
                self.const.CONF_DEVICE_TOKEN: "device-token",
                self.const.CONF_LOCAL_URL: "http://djconnect-981032.local",
            },
            options={},
        )
        hass = types.SimpleNamespace(data={self.const.DOMAIN: {}})

        runtime = self.integration._restore_runtime(hass, entry)

        self.assertNotIn("local_url", runtime.device_status)

    def test_initial_provisioning_skips_when_token_already_stored(self) -> None:
        class Runtime:
            device_token = "device-token"
            device_status = {}
            pair_called = False
            last_error = "previous"

            async def pair_device(self, hass):
                self.pair_called = True

            def update(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        runtime = Runtime()

        asyncio.run(self.integration._try_initial_device_provisioning(object(), runtime))

        self.assertFalse(runtime.pair_called)
        self.assertIsNone(runtime.last_error)

    def test_initial_provisioning_pairs_only_when_no_token_exists(self) -> None:
        class Runtime:
            device_token = None
            device_status = {}
            pair_called = False
            last_error = "previous"

            async def pair_device(self, hass):
                self.pair_called = True

            def update(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        runtime = Runtime()

        asyncio.run(self.integration._try_initial_device_provisioning(object(), runtime))

        self.assertTrue(runtime.pair_called)
        self.assertIsNone(runtime.last_error)

    def test_initial_provisioning_skips_when_device_confirmed_pairing(self) -> None:
        class Runtime:
            device_token = "device-token"
            device_status = {"ha_pairing_status": "paired"}
            pair_called = False
            last_error = "previous"

            async def pair_device(self, hass):
                self.pair_called = True

            def update(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        runtime = Runtime()

        asyncio.run(self.integration._try_initial_device_provisioning(object(), runtime))

        self.assertFalse(runtime.pair_called)
        self.assertIsNone(runtime.last_error)

    def test_initial_pairing_defers_unknown_local_url_without_last_error(self) -> None:
        class Runtime:
            device_token = None
            device_status = {}
            last_error = None

            async def pair_device(self, hass):
                raise RuntimeError("DJConnect device local_url is unknown")

            def update(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        runtime = Runtime()

        asyncio.run(self.integration._try_initial_device_provisioning(object(), runtime))

        self.assertEqual(runtime.device_status, {})
        self.assertIsNone(runtime.last_error)

    def test_initial_pairing_logs_empty_exception_type(self) -> None:
        class EmptyError(Exception):
            def __str__(self):
                return ""

        class Runtime:
            device_token = None
            device_status = {}
            last_error = None

            async def pair_device(self, hass):
                raise EmptyError()

            def update(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        runtime = Runtime()

        asyncio.run(self.integration._try_initial_device_provisioning(object(), runtime))

        self.assertIn("EmptyError", runtime.last_error)

    def test_persist_paired_device_updates_config_entry_data(self) -> None:
        class ConfigEntries:
            def __init__(self):
                self.calls = []

            def async_update_entry(self, entry, *, data):
                self.calls.append((entry, data))
                entry.data = data

        entry = types.SimpleNamespace(data={self.const.CONF_PAIR_CODE: "981032"})
        runtime = types.SimpleNamespace(entry=entry)
        config_entries = ConfigEntries()
        hass = types.SimpleNamespace(config_entries=config_entries)

        self.http._persist_paired_device(
            hass,
            runtime,
            "djconnect-lilygo-90B70990A994",
            "http://djconnect-lilygo-90B70990A994.local",
            "device-token",
        )

        self.assertEqual(config_entries.calls[0][1][self.const.CONF_PAIR_CODE], "981032")
        self.assertEqual(
            entry.data[self.const.CONF_DEVICE_ID],
            "djconnect-lilygo-90B70990A994",
        )
        self.assertEqual(entry.data[self.const.CONF_DEVICE_TOKEN], "device-token")
        self.assertEqual(
            entry.data[self.const.CONF_LOCAL_URL],
            "http://djconnect-lilygo-90B70990A994.local",
        )

    def test_pair_device_payload_omits_spotify_credentials(self) -> None:
        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def text(self):
                return '{"success": true}'

        class PairingInfoResponse(Response):
            async def text(self):
                return (
                    '{"device_id":"djconnect-lilygo-90B70990A994",'
                    '"pair_code":"123456","local_url":"http://djconnect.local"}'
                )

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append({"method": "GET", "url": url, **kwargs})
                return PairingInfoResponse()

            def post(self, url, **kwargs):
                self.calls.append({"method": "POST", "url": url, **kwargs})
                return Response()

        entry = types.SimpleNamespace(
            data={
                self.const.CONF_DEVICE_ID: "djconnect-123456",
                self.const.CONF_PAIR_CODE: "123456",
                self.const.CONF_DEVICE_LANGUAGE: "nl",
                self.const.CONF_HA_EXTERNAL_URL: "https://example.ui.nabu.casa",
                self.const.CONF_SPOTIFY_CLIENT_ID: "client-id",
                self.const.CONF_SPOTIFY_REFRESH_TOKEN: "refresh-token",
            },
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        runtime.latest_spotify_refresh_token = "rotated-token"
        runtime.device_status["local_url"] = "http://djconnect.local"
        session = Session()
        original_session = self.integration.async_get_clientsession
        self.integration.async_get_clientsession = lambda hass: session
        try:
            hass = types.SimpleNamespace(
                config=types.SimpleNamespace(
                    internal_url="http://homeassistant.local:8123",
                    external_url="https://fallback.example",
                )
            )
            result = asyncio.run(runtime.pair_device(hass))
        finally:
            self.integration.async_get_clientsession = original_session

        self.assertTrue(result["success"])
        self.assertEqual(
            session.calls[0]["url"],
            "http://djconnect.local/api/device/pairing-info",
        )
        payload = session.calls[1]["json"]
        self.assertEqual(payload["device_id"], "djconnect-lilygo-90B70990A994")
        self.assertEqual(payload["client_type"], "esp32")
        self.assertEqual(payload["ha_local_url"], "http://homeassistant.local:8123")
        self.assertEqual(payload["ha_remote_url"], "https://example.ui.nabu.casa")
        self.assertNotIn("ha_url", payload)
        self.assertEqual(payload["device_language"], "nl")
        self.assertEqual(payload["language"], "nl")
        self.assertNotIn("spotify", payload)
        self.assertNotIn("refresh_token", payload)
        self.assertNotIn("spotify_refresh_token", payload)
        self.assertNotIn("client_id", payload)
        self.assertNotIn("spotify_client_id", payload)

    def test_setup_code_pairing_accepts_real_device_id_after_token_sync(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                self.const.CONF_DEVICE_ID: "djconnect-328823",
                self.const.CONF_DEVICE_TOKEN: "token-new",
            },
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        runtime.device_token = "token-new"
        runtime.pairing_device_id = "djconnect-328823"
        runtime.device_status["device_id"] = "djconnect-328823"

        headers = {
            "Authorization": " Bearer token-new ",
            "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
        }
        with self.assertLogs(self.integration._LOGGER, level="DEBUG") as captured:
            allowed = runtime.authorize_device_request(
                headers,
                "djconnect-lilygo-90B70990A994",
            )

        self.assertTrue(allowed)
        self.assertEqual(runtime.pairing_device_id, "djconnect-lilygo-90B70990A994")
        self.assertEqual(runtime.device_status["device_id"], "djconnect-lilygo-90B70990A994")
        logs = "\n".join(captured.output)
        self.assertIn("token_match=True", logs)
        self.assertNotIn("token-new", logs)

    def test_repair_replaces_old_token_for_device_auth(self) -> None:
        entry = types.SimpleNamespace(entry_id="entry-1", data={}, options={})
        runtime = self.integration.DJConnectRuntime(entry=entry)
        runtime.device_token = "token-new"
        runtime.pairing_device_id = "djconnect-lilygo-90B70990A994"
        runtime.device_status["device_id"] = "djconnect-lilygo-90B70990A994"
        headers = {"X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994"}

        self.assertTrue(
            runtime.authorize_device_request(
                {**headers, "Authorization": "Bearer token-new"},
                "djconnect-lilygo-90B70990A994",
            )
        )
        self.assertFalse(
            runtime.authorize_device_request(
                {**headers, "Authorization": "Bearer token-old"},
                "djconnect-lilygo-90B70990A994",
            )
        )

    def test_status_command_and_voice_share_same_runtime_token_lookup(self) -> None:
        const = self.const
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                const.CONF_DEVICE_ID: "djconnect-328823",
                const.CONF_DEVICE_TOKEN: "token-shared",
            },
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        runtime.device_token = "token-shared"
        runtime.pairing_device_id = "djconnect-328823"
        runtime.device_status["device_id"] = "djconnect-328823"

        class ConfigEntries:
            def async_update_entry(self, entry, *, data):
                entry.data = data

        hass = types.SimpleNamespace(
            data={const.DOMAIN: {entry.entry_id: runtime, "runtime": runtime}},
            config_entries=ConfigEntries(),
        )
        headers = {
            "Authorization": "Bearer token-shared",
            "X-DJConnect-Device-ID": "djconnect-lilygo-90B70990A994",
            "Content-Type": "application/json",
        }

        class StatusRequest:
            def __init__(self):
                self.app = {"hass": hass}
                self.headers = headers

            async def json(self):
                return {
                    "device_id": "djconnect-lilygo-90B70990A994",
                    "client_type": "esp32",
                }

        async def command_handler(hass, runtime, command, value=None, *, play=None):
            return {"success": True, "playback": {"has_playback": False}}

        async def dj_response_handler(hass, runtime, text):
            return {"audio_url_value": ""}

        class CommandRequest:
            def __init__(self):
                self.app = {"hass": hass}
                self.headers = headers

            async def json(self):
                return {
                    "device_id": "djconnect-lilygo-90B70990A994",
                    "client_type": "esp32",
                    "command": "status",
                }

        class VoiceRequest:
            def __init__(self):
                self.app = {"hass": hass}
                self.headers = headers

            async def json(self):
                return {"text": "test"}

        original_command = self.http.handle_spotify_command
        original_dj_response = self.http.async_send_dj_response_best_effort
        self.http.handle_spotify_command = command_handler
        self.http.async_send_dj_response_best_effort = dj_response_handler
        try:
            status_response = asyncio.run(self.http.DJConnectStatusView(None).post(StatusRequest()))
            command_response = asyncio.run(self.http.DJConnectCommandView(None).post(CommandRequest()))
            voice_response = asyncio.run(self.http.DJConnectVoiceView(None).post(VoiceRequest()))
        finally:
            self.http.handle_spotify_command = original_command
            self.http.async_send_dj_response_best_effort = original_dj_response

        self.assertEqual(status_response["status_code"], 200)
        self.assertEqual(command_response["status_code"], 200)
        self.assertEqual(voice_response["status_code"], 200)

    def test_runtime_lookup_prefers_token_over_stale_duplicate_device_id(self) -> None:
        const = self.const
        stale = types.SimpleNamespace(
            device_token="old-token",
            pairing_device_id="djconnect-lilygo-90B70990A994",
            device_status={"device_id": "djconnect-lilygo-90B70990A994"},
            config={const.CONF_DEVICE_ID: "djconnect-lilygo-90B70990A994"},
            authorize_device_request=lambda headers, body_device_id=None: False,
        )
        active = types.SimpleNamespace(
            device_token="new-token",
            pairing_device_id="djconnect-lilygo-90B70990A994",
            device_status={"device_id": "djconnect-lilygo-90B70990A994"},
            config={const.CONF_DEVICE_ID: "djconnect-lilygo-90B70990A994"},
            authorize_device_request=lambda headers, body_device_id=None: True,
        )
        hass = types.SimpleNamespace(
            data={
                const.DOMAIN: {
                    "stale-entry": stale,
                    "active-entry": active,
                    "runtime": active,
                }
            }
        )

        resolved = self.http._runtime(
            hass,
            "djconnect-lilygo-90B70990A994",
            {"Authorization": "Bearer new-token"},
        )

        self.assertIs(resolved, active)

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
                self.const.CONF_DEVICE_ID: "djconnect-lilygo-90B70990A994",
                self.const.CONF_DEVICE_TOKEN: "device-token",
            },
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        runtime.device_token = "device-token"
        runtime.device_status["local_url"] = "http://djconnect-lilygo-90B70990A994.local"
        release = types.SimpleNamespace(
            version="3.0.6",
            firmware_url="https://example/djconnect-device-v3.0.6.bin",
            sha256="a" * 64,
            device="lilygo-t-embed-s3",
            firmware_asset="djconnect-device-v3.0.6.bin",
        )
        session = Session()
        original_session = self.integration.async_get_clientsession
        self.integration.async_get_clientsession = lambda hass: session
        try:
            asyncio.run(runtime.start_ota(object(), release))
        finally:
            self.integration.async_get_clientsession = original_session

        call = session.calls[0]
        self.assertEqual(call["url"], "http://djconnect-lilygo-90B70990A994.local/api/device/ota")
        self.assertEqual(call["headers"]["Authorization"], "Bearer device-token")
        self.assertEqual(
            call["json"],
            {
                "version": "3.0.6",
                "url": "https://example/djconnect-device-v3.0.6.bin",
                "sha256": "a" * 64,
                "device": "lilygo-t-embed-s3",
                "asset": "djconnect-device-v3.0.6.bin",
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
            data={self.const.CONF_DEVICE_ID: "djconnect-lilygo-90B70990A994"},
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        runtime.device_status["local_url"] = "http://djconnect-lilygo-90B70990A994.local"
        release = types.SimpleNamespace(
            version="3.0.6",
            firmware_url="https://example/djconnect-device-v3.0.6.bin",
            sha256="a" * 64,
            device="djconnect-device",
            firmware_asset="djconnect-device-v3.0.6.bin",
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
            data={self.const.CONF_DEVICE_ID: "djconnect-123456"},
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        info = types.SimpleNamespace(
            name="djconnect-123456._djconnect._tcp.local.",
            server="djconnect-123456.local.",
            port=8080,
        )

        url = self.integration._url_from_service_info(info, runtime)

        self.assertEqual(url, "http://djconnect-123456.local:8080")

    def test_async_get_mdns_service_info_uses_ha_zeroconf_getter(self) -> None:
        class AsyncZeroconf:
            async def async_get_service_info(self, service_type, service_name):
                return types.SimpleNamespace(
                    name=service_name,
                    server="djconnect-lilygo-90B70990A994.local.",
                    port=80,
                )

        info = asyncio.run(
            self.integration._async_get_mdns_service_info(
                AsyncZeroconf(),
                "DJConnect 90B70990A994._djconnect._tcp.local.",
            )
        )

        self.assertEqual(info.server, "djconnect-lilygo-90B70990A994.local.")

    def test_url_from_service_info_matches_friendly_mdns_name(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "djconnect-123456"},
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        info = types.SimpleNamespace(
            name="DJConnect 123456._djconnect._tcp.local.",
            server="djconnect-123456.local.",
            port=80,
        )

        url = self.integration._url_from_service_info(info, runtime)

        self.assertEqual(url, "http://djconnect-123456.local")

    def test_url_from_service_info_ignores_other_devices(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "djconnect-123456"},
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)
        info = types.SimpleNamespace(
            name="djconnect-other._djconnect._tcp.local.",
            server="djconnect-other.local.",
            port=80,
        )

        self.assertIsNone(self.integration._url_from_service_info(info, runtime))

    def test_mdns_service_name_candidates_include_device_and_friendly_names(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "djconnect-123456"},
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)

        names = self.integration._mdns_service_name_candidates(runtime)

        self.assertIn("djconnect-123456._djconnect._tcp.local.", names)
        self.assertIn("DJConnect 123456._djconnect._tcp.local.", names)

    def test_device_local_url_falls_back_to_mdns_hostname(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "djconnect-lilygo-90B70990A994"},
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)

        url = asyncio.run(runtime.async_device_local_url(hass=object()))

        self.assertEqual(url, "http://djconnect-lilygo-90B70990A994.local")

    def test_device_local_url_does_not_fallback_to_pair_code_hostname(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "djconnect-981032"},
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)

        url = asyncio.run(runtime.async_device_local_url(hass=object()))

        self.assertIsNone(url)

    def test_device_local_url_ignores_stored_pair_code_hostname(self) -> None:
        entry = types.SimpleNamespace(
            data={
                self.const.CONF_DEVICE_ID: "djconnect-981032",
                self.const.CONF_LOCAL_URL: "http://djconnect-981032.local",
            },
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)

        url = asyncio.run(runtime.async_device_local_url(hass=object()))

        self.assertIsNone(url)

    def test_device_local_url_uses_mdns_browse_for_pair_code_entry(self) -> None:
        entry = types.SimpleNamespace(
            data={self.const.CONF_DEVICE_ID: "djconnect-981032"},
            options={},
        )
        runtime = self.integration.DJConnectRuntime(entry=entry)

        async def discover(hass, runtime):
            return "http://djconnect-lilygo-90B70990A994.local"

        original_discover = self.integration.async_discover_device_url
        self.integration.async_discover_device_url = discover
        try:
            url = asyncio.run(runtime.async_device_local_url(hass=object()))
        finally:
            self.integration.async_discover_device_url = original_discover

        self.assertEqual(url, "http://djconnect-lilygo-90B70990A994.local")

    def test_tts_audio_store_returns_wav_and_unknown_404(self) -> None:
        hass = types.SimpleNamespace(data={})

        token = self.dj_response.store_tts_audio(hass, b"RIFFxxxxWAVEdata", 120)

        status, audio = self.dj_response.get_tts_audio(hass, token)
        self.assertEqual(status, 200)
        self.assertEqual(audio.data, b"RIFFxxxxWAVEdata")
        self.assertEqual(audio.content_type, "audio/wav")
        self.assertEqual(audio.extension, "wav")
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
