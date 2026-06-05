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

    class OptionsFlow:
        @property
        def config_entry(self):
            return None

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
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )
    aiohttp_client.async_get_clientsession = lambda hass: None

    package = types.ModuleType("custom_components.spotify_dj")
    package.__path__ = [str(ROOT / "custom_components" / "spotify_dj")]
    package.register_http_views = lambda hass: None
    sys.modules["custom_components.spotify_dj"] = package


class ConfigFlowHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_homeassistant_stubs()
        cls.config_flow = importlib.import_module("custom_components.spotify_dj.config_flow")
        cls.const = importlib.import_module("custom_components.spotify_dj.const")

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
            self.const.CONF_MQTT_HOST,
            self.const.CONF_MQTT_PORT,
            self.const.CONF_MQTT_USERNAME,
            self.const.CONF_MQTT_PASSWORD,
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
        self.assertTrue(advanced_only.issubset(advanced_keys))
        self.assertIn(self.const.CONF_DJ_RESPONSE_ENABLED, basic_keys)

    def test_voice_defaults_fill_empty_values(self) -> None:
        data = self.config_flow._voice_defaults(
            {
                self.const.CONF_TTS_LANGUAGE: "",
                self.const.CONF_DJ_STYLE: "does_not_exist",
                self.const.CONF_MAX_AUDIO_BYTES: "not-an-int",
                self.const.CONF_MIN_BATTERY_FOR_OTA: "55",
                self.const.CONF_MQTT_PORT: "1884",
            }
        )

        self.assertEqual(data[self.const.CONF_TTS_LANGUAGE], self.const.DEFAULT_TTS_LANGUAGE)
        self.assertEqual(data[self.const.CONF_DJ_STYLE], self.const.DEFAULT_DJ_STYLE)
        self.assertEqual(data[self.const.CONF_DJ_PROFILE], self.const.DEFAULT_DJ_STYLE)
        self.assertEqual(data[self.const.CONF_MAX_AUDIO_BYTES], self.const.DEFAULT_MAX_AUDIO_BYTES)
        self.assertTrue(data[self.const.CONF_ALLOW_OTA_ON_BATTERY])
        self.assertEqual(data[self.const.CONF_MIN_BATTERY_FOR_OTA], 55)
        self.assertEqual(data[self.const.CONF_MQTT_PORT], 1884)
        self.assertTrue(data[self.const.CONF_DJ_RESPONSE_ENABLED])
        self.assertEqual(
            data[self.const.CONF_DJ_RESPONSE_TTL_SECONDS],
            self.const.DEFAULT_DJ_RESPONSE_TTL_SECONDS,
        )

    def test_mqtt_defaults_use_static_homeassistant_host(self) -> None:
        defaults = self.config_flow._merged_mqtt_defaults(
            types.SimpleNamespace(),
            {},
        )

        self.assertEqual(
            defaults[self.const.CONF_MQTT_HOST],
            self.const.DEFAULT_MQTT_HOST,
        )
        self.assertEqual(defaults[self.const.CONF_MQTT_PORT], self.const.DEFAULT_MQTT_PORT)

    def test_mqtt_defaults_do_not_override_existing_values(self) -> None:
        defaults = self.config_flow._merged_mqtt_defaults(
            types.SimpleNamespace(),
            {
                self.const.CONF_MQTT_HOST: "manual-mqtt",
                self.const.CONF_MQTT_PORT: 1884,
            },
        )

        self.assertEqual(defaults[self.const.CONF_MQTT_HOST], "manual-mqtt")
        self.assertEqual(defaults[self.const.CONF_MQTT_PORT], 1884)

    def test_voice_errors_require_spotify_player(self) -> None:
        errors = self.config_flow._voice_errors({self.const.CONF_SPOTIFY_PLAYER: ""})

        self.assertEqual(
            errors,
            {self.const.CONF_SPOTIFY_PLAYER: "spotify_player_required"},
        )
        self.assertEqual(
            self.config_flow._voice_errors(
                {self.const.CONF_SPOTIFY_PLAYER: "media_player.spotify"}
            ),
            {},
        )

    def test_user_schema_hides_manual_device_url_until_advanced(self) -> None:
        flow = self.config_flow.SpotifyDJConfigFlow()
        flow.hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))

        basic_keys = {marker.key for marker in flow._user_schema()}
        flow.show_advanced_options = True
        advanced_keys = {marker.key for marker in flow._user_schema()}

        self.assertNotIn(self.const.CONF_LOCAL_URL, basic_keys)
        self.assertIn(self.const.CONF_LOCAL_URL, advanced_keys)
        self.assertIn(self.const.CONF_DEVICE_LANGUAGE, basic_keys)

    def test_user_schema_prefills_manual_device_url_from_pair_code(self) -> None:
        flow = self.config_flow.SpotifyDJConfigFlow()
        flow.hass = types.SimpleNamespace(config=types.SimpleNamespace(language="en-US"))
        flow.show_advanced_options = True
        flow._last_pair_code = "123456"

        schema = flow._user_schema()
        local_url_marker = next(
            marker for marker in schema if marker.key == self.const.CONF_LOCAL_URL
        )

        self.assertEqual(local_url_marker.default, "http://spotifydj-123456.local")

    def test_default_local_url_requires_six_digit_pair_code(self) -> None:
        self.assertEqual(
            self.config_flow._default_local_url("123456"),
            "http://spotifydj-123456.local",
        )
        self.assertEqual(self.config_flow._default_local_url("abc123"), "")
        self.assertEqual(self.config_flow._default_local_url("12345"), "")

    def test_device_language_default_uses_ha_language_when_supported(self) -> None:
        nl_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="nl-NL"))
        en_hass = types.SimpleNamespace(config=types.SimpleNamespace(language="en-US"))

        self.assertEqual(self.config_flow._ha_device_language(nl_hass), "nl")
        self.assertEqual(self.config_flow._ha_device_language(en_hass), "en")

    def test_ble_wifi_schema_uses_discovered_devices_when_available(self) -> None:
        schema = self.config_flow._ble_wifi_schema({"AA:BB": "SpotifyDJ 1234"})

        keys = {marker.key for marker in schema}
        self.assertIn(self.const.CONF_BLE_ADDRESS, keys)
        self.assertIn(self.const.CONF_WIFI_SSID, keys)
        self.assertIn(self.const.CONF_WIFI_PASSWORD, keys)

    def test_spotify_client_id_is_advanced_override(self) -> None:
        basic_schema = self.config_flow._spotify_schema(include_advanced=False)
        advanced_schema = self.config_flow._spotify_schema(include_advanced=True)

        basic_keys = {marker.key for marker in basic_schema}
        advanced_keys = {marker.key for marker in advanced_schema}

        self.assertNotIn(self.const.CONF_SPOTIFY_CLIENT_ID, basic_keys)
        self.assertIn(self.const.CONF_SPOTIFY_CLIENT_ID, advanced_keys)

    def test_options_flow_init_does_not_assign_read_only_config_entry(self) -> None:
        entry = types.SimpleNamespace(data={}, options={})

        flow = self.config_flow.SpotifyDJOptionsFlow(entry)

        self.assertIs(flow._config_entry, entry)


if __name__ == "__main__":
    unittest.main()
