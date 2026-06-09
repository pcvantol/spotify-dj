from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_homeassistant_stubs() -> None:
    homeassistant = sys.modules.setdefault(
        "homeassistant",
        types.ModuleType("homeassistant"),
    )
    config_entries = sys.modules.setdefault(
        "homeassistant.config_entries",
        types.ModuleType("homeassistant.config_entries"),
    )
    core = sys.modules.setdefault(
        "homeassistant.core",
        types.ModuleType("homeassistant.core"),
    )
    data_entry_flow = sys.modules.setdefault(
        "homeassistant.data_entry_flow",
        types.ModuleType("homeassistant.data_entry_flow"),
    )
    voluptuous = sys.modules.setdefault("voluptuous", types.ModuleType("voluptuous"))
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_external_step(self, **kwargs):
            return {"type": "external", **kwargs}

        def async_external_step_done(self, **kwargs):
            return {"type": "external_done", **kwargs}

    class OptionsFlow:
        @property
        def config_entry(self):
            return None

        def async_external_step(self, **kwargs):
            return {"type": "external", **kwargs}

        def async_external_step_done(self, **kwargs):
            return {"type": "external_done", **kwargs}

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

    class ConfigEntry:
        pass

    class Schema:
        def __init__(self, schema):
            self.schema = schema

    class Marker:
        def __init__(self, key, default=None):
            self.key = key
            self.default = default

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.ConfigEntry = ConfigEntry
    core.callback = lambda func: func
    core.HomeAssistant = object
    data_entry_flow.FlowResult = dict
    voluptuous.Schema = Schema
    voluptuous.Required = Marker
    voluptuous.Optional = Marker
    voluptuous.In = lambda values: values
    aiohttp.ClientTimeout = ClientTimeout

    homeassistant.config_entries = config_entries
    helpers = sys.modules.setdefault(
        "homeassistant.helpers",
        types.ModuleType("homeassistant.helpers"),
    )
    network = sys.modules.setdefault(
        "homeassistant.helpers.network",
        types.ModuleType("homeassistant.helpers.network"),
    )
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )
    components = sys.modules.setdefault(
        "homeassistant.components",
        types.ModuleType("homeassistant.components"),
    )
    cloud = sys.modules.setdefault(
        "homeassistant.components.cloud",
        types.ModuleType("homeassistant.components.cloud"),
    )
    aiohttp_client.async_get_clientsession = lambda hass: None
    network.async_get_url = lambda *args, **kwargs: ""
    cloud.async_remote_ui_url = lambda hass: ""
    helpers.network = network
    components.cloud = cloud

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    package.register_http_views = lambda hass: None
    sys.modules["custom_components.djconnect"] = package


class ConfigFlowHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_homeassistant_stubs()
        cls.config_flow = importlib.import_module("custom_components.djconnect.config_flow")
        cls.const = importlib.import_module("custom_components.djconnect.const")

    def test_https_url_validation_requires_scheme_and_host(self) -> None:
        self.assertTrue(self.config_flow._is_https_url("https://example.ui.nabu.casa"))
        self.assertFalse(self.config_flow._is_https_url("http://example.ui.nabu.casa"))
        self.assertFalse(self.config_flow._is_https_url("https://"))
        self.assertFalse(self.config_flow._is_https_url("example.ui.nabu.casa"))

    def test_options_with_current_preserves_existing_free_text_value(self) -> None:
        options = self.config_flow._options_with_current({"stable": "Stable"}, "nightly")

        self.assertEqual(options["stable"], "Stable")
        self.assertEqual(options["nightly"], "nightly")

    def test_tts_voice_options_use_entity_supported_voices(self) -> None:
        class State:
            attributes = {
                "supported_voices": [
                    {"voice_id": "anna", "name": "Anna"},
                    "bram",
                ]
            }

        class States:
            def get(self, entity_id):
                return State() if entity_id == "tts.home_assistant_cloud" else None

        hass = types.SimpleNamespace(states=States())

        options = self.config_flow._tts_voice_options(
            hass,
            "tts.home_assistant_cloud",
            "custom_voice",
        )

        self.assertEqual(options[""], "Default")
        self.assertEqual(options["anna"], "Anna")
        self.assertEqual(options["bram"], "bram")
        self.assertEqual(options["custom_voice"], "custom_voice")

    def test_tts_voice_sync_clears_stale_voice_after_engine_change(self) -> None:
        class State:
            attributes = {"supported_voices": ["puck", "zephyr"]}

        class States:
            def get(self, entity_id):
                return State() if entity_id == "tts.google_ai" else None

        hass = types.SimpleNamespace(states=States())
        values = {
            self.const.CONF_TTS_ENGINE: "tts.google_ai",
            self.const.CONF_TTS_VOICE: "MaartenNeural",
        }

        synced = self.config_flow._sync_tts_voice_with_engine(hass, values)

        self.assertEqual(synced[self.const.CONF_TTS_VOICE], "")

    def test_tts_voice_sync_keeps_voice_when_engine_voices_are_unknown(self) -> None:
        hass = types.SimpleNamespace(states=None)
        values = {
            self.const.CONF_TTS_ENGINE: "tts.custom",
            self.const.CONF_TTS_VOICE: "custom_voice",
        }

        synced = self.config_flow._sync_tts_voice_with_engine(hass, values)

        self.assertEqual(synced[self.const.CONF_TTS_VOICE], "custom_voice")

    def test_voice_schema_preserves_explicit_default_values(self) -> None:
        hass = types.SimpleNamespace(states=None)
        defaults = self.config_flow._voice_defaults(
            {
                self.const.CONF_STT_ENGINE: "",
                self.const.CONF_TTS_ENGINE: "",
                self.const.CONF_TTS_VOICE: "",
            },
            preserve_empty=True,
        )

        schema = asyncio.run(self.config_flow._voice_schema(hass, defaults))
        marker_defaults = {marker.key: marker.default for marker in schema.schema}

        self.assertEqual(marker_defaults[self.const.CONF_STT_ENGINE], "")
        self.assertEqual(marker_defaults[self.const.CONF_TTS_ENGINE], "")
        self.assertEqual(marker_defaults[self.const.CONF_TTS_VOICE], "")

    def test_voice_schema_hides_firmware_and_ota_fields_until_advanced(self) -> None:
        hass = types.SimpleNamespace(states=None)

        basic_schema = asyncio.run(
            self.config_flow._voice_schema(
                hass,
                self.config_flow._voice_defaults(),
                include_advanced=False,
            )
        )
        advanced_schema = asyncio.run(
            self.config_flow._voice_schema(
                hass,
                self.config_flow._voice_defaults(),
                include_advanced=True,
            )
        )

        basic_keys = {marker.key for marker in basic_schema.schema}
        advanced_keys = {marker.key for marker in advanced_schema.schema}
        advanced_only = {
            self.const.CONF_SPOTIFY_SOURCE,
            self.const.CONF_FIRMWARE_REPO,
            self.const.CONF_FIRMWARE_ASSET_PREFIX,
            self.const.CONF_FIRMWARE_DEVICE,
            self.const.CONF_FIRMWARE_CHANNEL,
            self.const.CONF_MAX_AUDIO_BYTES,
            self.const.CONF_ALLOW_OTA_ON_BATTERY,
            self.const.CONF_MIN_BATTERY_FOR_OTA,
            self.const.CONF_DJ_RESPONSE_TTL_SECONDS,
        }

        self.assertTrue(advanced_only.isdisjoint(basic_keys))
        self.assertIn(self.const.CONF_STT_ENGINE, basic_keys)
        self.assertIn(self.const.CONF_TTS_ENGINE, basic_keys)
        self.assertTrue(advanced_only.issubset(advanced_keys))
        self.assertIn(self.const.CONF_DJ_RESPONSE_ENABLED, basic_keys)

    def test_voice_defaults_fill_empty_values(self) -> None:
        data = self.config_flow._voice_defaults(
            {
                self.const.CONF_TTS_LANGUAGE: "",
                self.const.CONF_DJ_STYLE: "does_not_exist",
                self.const.CONF_MAX_AUDIO_BYTES: "not-an-int",
                self.const.CONF_MIN_BATTERY_FOR_OTA: "55",
            }
        )

        self.assertEqual(data[self.const.CONF_TTS_LANGUAGE], self.const.DEFAULT_TTS_LANGUAGE)
        self.assertEqual(data[self.const.CONF_DJ_STYLE], self.const.DEFAULT_DJ_STYLE)
        self.assertEqual(data[self.const.CONF_DJ_PROFILE], self.const.DEFAULT_DJ_STYLE)
        self.assertEqual(data[self.const.CONF_MAX_AUDIO_BYTES], self.const.DEFAULT_MAX_AUDIO_BYTES)
        self.assertTrue(data[self.const.CONF_ALLOW_OTA_ON_BATTERY])
        self.assertEqual(data[self.const.CONF_MIN_BATTERY_FOR_OTA], 55)
        self.assertTrue(data[self.const.CONF_DJ_RESPONSE_ENABLED])
        self.assertEqual(
            data[self.const.CONF_DJ_RESPONSE_TTL_SECONDS],
            self.const.DEFAULT_DJ_RESPONSE_TTL_SECONDS,
        )

    def test_voice_errors_allow_device_owned_spotify_playback(self) -> None:
        self.assertEqual(self.config_flow._voice_errors({}), {})

    def test_user_schema_hides_manual_device_url_until_advanced(self) -> None:
        flow = self.config_flow.DJConnectConfigFlow()
        flow.hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))

        basic_keys = {marker.key for marker in flow._user_schema()}
        flow._show_advanced_options = True
        advanced_keys = {marker.key for marker in flow._user_schema()}

        self.assertNotIn(self.const.CONF_LOCAL_URL, basic_keys)
        self.assertIn(self.const.CONF_LOCAL_URL, advanced_keys)
        self.assertIn(self.const.CONF_DEVICE_LANGUAGE, basic_keys)

    def test_user_schema_prefills_manual_device_url_from_pair_code(self) -> None:
        flow = self.config_flow.DJConnectConfigFlow()
        flow.hass = types.SimpleNamespace(config=types.SimpleNamespace(language="en-US"))
        flow._show_advanced_options = True
        flow._last_pair_code = "90B70990A994"

        schema = flow._user_schema()
        local_url_marker = next(
            marker for marker in schema if marker.key == self.const.CONF_LOCAL_URL
        )

        self.assertEqual(
            local_url_marker.default,
            "http://djconnect-lilygo-90B70990A994.local",
        )

    def test_default_local_url_accepts_only_device_suffix(self) -> None:
        self.assertEqual(self.config_flow._default_local_url("123456"), "")
        self.assertEqual(
            self.config_flow._default_local_url("90B70990A994"),
            "http://djconnect-lilygo-90B70990A994.local",
        )
        self.assertTrue(self.config_flow._valid_pair_code("123456"))
        self.assertTrue(self.config_flow._valid_pair_code("90B70990A994"))
        self.assertFalse(self.config_flow._valid_pair_code("abc123"))
        self.assertEqual(self.config_flow._default_local_url("12345"), "")

    def test_device_language_default_uses_ha_language_when_supported(self) -> None:
        nl_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))
        en_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="en-US"))

        self.assertEqual(self.config_flow._ha_device_language(nl_hass), "nl")
        self.assertEqual(self.config_flow._ha_device_language(en_hass), "en")

    def test_setup_method_labels_follow_ha_language(self) -> None:
        nl_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))
        en_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="en-US"))

        self.assertEqual(
            self.config_flow._setup_method_names(nl_hass)[
                self.const.SETUP_METHOD_PAIR_EXISTING
            ],
            "Bestaand WiFi device koppelen",
        )
        self.assertEqual(
            self.config_flow._setup_method_names(en_hass)[
                self.const.SETUP_METHOD_PAIR_EXISTING
            ],
            "Pair existing WiFi device",
        )

    def test_ble_action_labels_follow_ha_language(self) -> None:
        nl_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))
        en_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="en-US"))

        self.assertEqual(
            self.config_flow._ble_action_names(nl_hass)[
                self.config_flow.BLE_ACTION_CONTINUE_PAIRING
            ],
            "Doorgaan naar koppelen",
        )
        self.assertEqual(
            self.config_flow._ble_action_names(en_hass)[
                self.config_flow.BLE_ACTION_RETRY_SCAN
            ],
            "Rescan Bluetooth devices",
        )

    def test_options_action_labels_follow_ha_language(self) -> None:
        nl_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))
        en_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="en-US"))

        self.assertEqual(
            self.config_flow._options_action_names(nl_hass)[
                self.config_flow.OPTIONS_ACTION_REPAIR
            ],
            "Opnieuw koppelen met nieuwe koppelcode",
        )
        self.assertEqual(
            self.config_flow._options_action_names(en_hass)[
                self.config_flow.OPTIONS_ACTION_RETRY_PAIRING
            ],
            "Retry pairing with current code",
        )
        self.assertEqual(
            self.config_flow._options_action_names(en_hass)[
                self.config_flow.OPTIONS_ACTION_SPOTIFY_REAUTH
            ],
            "Reauthorize Spotify",
        )
        self.assertEqual(
            self.config_flow._options_action_names(en_hass)[
                self.config_flow.OPTIONS_ACTION_SAVE
            ],
            "Save options",
        )

    def test_ble_wifi_schema_uses_discovered_devices_when_available(self) -> None:
        schema = self.config_flow._ble_wifi_schema({"AA:BB": "DJConnect 1234"})

        keys = {marker.key for marker in schema}
        self.assertIn(self.config_flow.BLE_ACTION_FIELD, keys)
        self.assertIn(self.const.CONF_BLE_ADDRESS, keys)
        self.assertIn(self.const.CONF_WIFI_SSID, keys)
        self.assertIn(self.const.CONF_WIFI_PASSWORD, keys)

    def test_ble_wifi_schema_selects_single_discovered_device_by_default(self) -> None:
        schema = self.config_flow._ble_wifi_schema({"AA:BB": "DJConnect A994"})

        defaults = {marker.key: marker.default for marker in schema}

        self.assertEqual(defaults[self.const.CONF_BLE_ADDRESS], "AA:BB")

    def test_ble_wifi_schema_keeps_placeholder_when_multiple_devices_exist(self) -> None:
        schema = self.config_flow._ble_wifi_schema(
            {"AA:BB": "DJConnect A994", "CC:DD": "DJConnect 1234"}
        )

        defaults = {marker.key: marker.default for marker in schema}

        self.assertEqual(defaults[self.const.CONF_BLE_ADDRESS], "")

    def test_pair_schema_allows_returning_to_ble_setup(self) -> None:
        flow = self.config_flow.DJConnectConfigFlow()
        flow.hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))

        schema = flow._user_schema()
        keys = {marker.key for marker in schema}

        self.assertIn(self.const.CONF_SETUP_METHOD, keys)
        self.assertIn(self.const.CONF_PAIR_CODE, keys)

    def test_pair_step_can_route_back_to_ble_setup(self) -> None:
        flow = self.config_flow.DJConnectConfigFlow()
        flow.hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))

        async def fake_ble_wifi(user_input=None):
            return {"type": "form", "step_id": "ble_wifi"}

        flow.async_step_ble_wifi = fake_ble_wifi

        result = asyncio.run(
            flow.async_step_pair({self.const.CONF_SETUP_METHOD: self.config_flow.SETUP_METHOD_BLE_WIFI})
        )

        self.assertEqual(result["step_id"], "ble_wifi")

    def test_spotify_client_id_is_advanced_override(self) -> None:
        basic_schema = self.config_flow._spotify_schema(include_advanced=False)
        advanced_schema = self.config_flow._spotify_schema(include_advanced=True)

        basic_keys = {marker.key for marker in basic_schema}
        advanced_keys = {marker.key for marker in advanced_schema}

        self.assertNotIn(self.const.CONF_SPOTIFY_CLIENT_ID, basic_keys)
        self.assertIn(self.const.CONF_SPOTIFY_CLIENT_ID, advanced_keys)

    def test_voice_schema_can_include_options_action(self) -> None:
        hass = types.SimpleNamespace(states=None, config=types.SimpleNamespace(language="nl-NL"))

        schema = asyncio.run(
            self.config_flow._voice_schema(
                hass,
                self.config_flow._voice_defaults({}),
                include_options_action=True,
            )
        ).schema
        keys = {marker.key for marker in schema}

        self.assertIn(self.config_flow.OPTIONS_ACTION_FIELD, keys)

    def test_spotify_schema_prefills_external_url(self) -> None:
        schema = self.config_flow._spotify_schema_with_defaults(
            external_url="https://example.ui.nabu.casa"
        )
        marker = next(
            marker for marker in schema if marker.key == self.const.CONF_HA_EXTERNAL_URL
        )

        self.assertEqual(marker.default, "https://example.ui.nabu.casa")

    def test_default_external_url_uses_hass_config_fallback(self) -> None:
        hass = types.SimpleNamespace(
            config=types.SimpleNamespace(external_url="https://example.ui.nabu.casa/")
        )

        self.assertEqual(
            asyncio.run(self.config_flow._async_default_external_url(hass)),
            "https://example.ui.nabu.casa",
        )

    def test_default_external_url_uses_hass_config_api_fallback(self) -> None:
        hass = types.SimpleNamespace(
            config=types.SimpleNamespace(
                api=types.SimpleNamespace(external_url="https://api.ui.nabu.casa/")
            )
        )

        self.assertEqual(
            asyncio.run(self.config_flow._async_default_external_url(hass)),
            "https://api.ui.nabu.casa",
        )

    def test_default_external_url_uses_hass_data_fallback(self) -> None:
        hass = types.SimpleNamespace(
            config=types.SimpleNamespace(),
            data={"external_url": "https://data.ui.nabu.casa/"},
        )

        self.assertEqual(
            asyncio.run(self.config_flow._async_default_external_url(hass)),
            "https://data.ui.nabu.casa",
        )

    def test_spotify_step_prefills_external_url_from_hass(self) -> None:
        flow = self.config_flow.DJConnectConfigFlow()
        flow.hass = types.SimpleNamespace(
            config=types.SimpleNamespace(
                api=types.SimpleNamespace(external_url="https://api.ui.nabu.casa/")
            )
        )

        result = asyncio.run(flow.async_step_spotify())
        schema = result["data_schema"].schema
        marker = next(
            marker for marker in schema if marker.key == self.const.CONF_HA_EXTERNAL_URL
        )

        self.assertEqual(marker.default, "https://api.ui.nabu.casa")

    def test_spotify_oauth_external_step_has_title(self) -> None:
        flow = self.config_flow.DJConnectConfigFlow()
        flow.hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))
        flow._oauth = {
            "authorize_url": "https://accounts.spotify.com/authorize",
            "redirect_uri": "https://example.ui.nabu.casa/api/djconnect/spotify/callback",
        }

        result = asyncio.run(flow.async_step_spotify_oauth())

        self.assertEqual(result["type"], "external")
        self.assertEqual(result["title"], "DJConnect autoriseren bij Spotify")

    def test_default_external_url_prefers_network_helper(self) -> None:
        from homeassistant.helpers import network

        original = network.async_get_url

        async def network_url(*args, **kwargs):
            return "https://network.ui.nabu.casa/"

        network.async_get_url = network_url
        try:
            self.assertEqual(
                asyncio.run(
                    self.config_flow._async_default_external_url(
                        types.SimpleNamespace(config=types.SimpleNamespace())
                    )
                ),
                "https://network.ui.nabu.casa",
            )
        finally:
            network.async_get_url = original

    def test_default_external_url_uses_sync_network_helper_with_cloud_preference(self) -> None:
        from homeassistant.helpers import network

        original_async = network.async_get_url
        original_sync = getattr(network, "get_url", None)

        def network_url(hass, **kwargs):
            self.assertTrue(kwargs["prefer_external"])
            self.assertTrue(kwargs["prefer_cloud"])
            self.assertFalse(kwargs["allow_internal"])
            self.assertTrue(kwargs["allow_cloud"])
            self.assertTrue(kwargs["require_ssl"])
            return "https://cloud-sync.ui.nabu.casa/"

        network.async_get_url = None
        network.get_url = network_url
        try:
            self.assertEqual(
                asyncio.run(
                    self.config_flow._async_default_external_url(
                        types.SimpleNamespace(config=types.SimpleNamespace())
                    )
                ),
                "https://cloud-sync.ui.nabu.casa",
            )
        finally:
            network.async_get_url = original_async
            if original_sync is None:
                delattr(network, "get_url")
            else:
                network.get_url = original_sync

    def test_default_external_url_uses_cloud_remote_ui_fallback(self) -> None:
        from homeassistant.components import cloud
        from homeassistant.helpers import network

        original_network = network.async_get_url
        original_cloud = cloud.async_remote_ui_url

        async def no_network_url(*args, **kwargs):
            return ""

        async def cloud_url(hass):
            return "https://cloud.ui.nabu.casa/"

        network.async_get_url = no_network_url
        cloud.async_remote_ui_url = cloud_url
        try:
            self.assertEqual(
                asyncio.run(
                    self.config_flow._async_default_external_url(
                        types.SimpleNamespace(config=types.SimpleNamespace())
                    )
                ),
                "https://cloud.ui.nabu.casa",
            )
        finally:
            network.async_get_url = original_network
            cloud.async_remote_ui_url = original_cloud

    def test_default_external_url_uses_sync_cloud_remote_ui_fallback(self) -> None:
        from homeassistant.components import cloud
        from homeassistant.helpers import network

        original_network = network.async_get_url
        original_cloud = cloud.async_remote_ui_url

        async def no_network_url(*args, **kwargs):
            return ""

        def cloud_url(hass):
            return "https://sync-cloud.ui.nabu.casa/"

        network.async_get_url = no_network_url
        cloud.async_remote_ui_url = cloud_url
        try:
            self.assertEqual(
                asyncio.run(
                    self.config_flow._async_default_external_url(
                        types.SimpleNamespace(config=types.SimpleNamespace())
                    )
                ),
                "https://sync-cloud.ui.nabu.casa",
            )
        finally:
            network.async_get_url = original_network
            cloud.async_remote_ui_url = original_cloud

    def test_options_flow_init_does_not_assign_read_only_config_entry(self) -> None:
        entry = types.SimpleNamespace(data={}, options={})

        flow = self.config_flow.DJConnectOptionsFlow(entry)

        self.assertIs(flow._config_entry, entry)

    def test_options_spotify_reauth_finishes_with_done_step(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                self.const.CONF_HA_EXTERNAL_URL: "https://example.ui.nabu.casa",
                self.const.CONF_SPOTIFY_CLIENT_ID: "client-id",
            },
            options={},
        )
        flow = self.config_flow.DJConnectOptionsFlow(entry)
        flow.flow_id = "flow-1"
        flow.hass = types.SimpleNamespace(data={})

        external = asyncio.run(flow.async_step_spotify_reauth())
        self.assertEqual(external["type"], "external")
        self.assertEqual(external["step_id"], "spotify_reauth")
        self.assertEqual(external["title"], "Reauthorize Spotify")
        self.assertIn("https://accounts.spotify.com/authorize", external["url"])
        self.assertIn(
            flow._oauth["state"],
            flow.hass.data[self.const.DOMAIN]["spotify_oauth_pending"],
        )

        done = asyncio.run(
            flow.async_step_spotify_reauth({"state": flow._oauth["state"]})
        )
        self.assertEqual(done["type"], "external_done")
        self.assertEqual(done["next_step_id"], "spotify_reauth_done")

        form = asyncio.run(flow.async_step_spotify_reauth_done())
        self.assertEqual(form["type"], "form")
        self.assertEqual(form["step_id"], "spotify_reauth_done")

        submit = asyncio.run(flow.async_step_spotify_reauth_done({}))
        self.assertEqual(submit["type"], "create_entry")


if __name__ == "__main__":
    unittest.main()
