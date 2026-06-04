from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_homeassistant_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")
    voluptuous = types.ModuleType("voluptuous")
    aiohttp = types.ModuleType("aiohttp")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    class OptionsFlow:
        pass

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
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow
    sys.modules["voluptuous"] = voluptuous
    sys.modules["aiohttp"] = aiohttp

    helpers = types.ModuleType("homeassistant.helpers")
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: None
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

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
            self.const.CONF_FIRMWARE_REPO,
            self.const.CONF_FIRMWARE_ASSET_PREFIX,
            self.const.CONF_FIRMWARE_DEVICE,
            self.const.CONF_FIRMWARE_CHANNEL,
            self.const.CONF_MAX_AUDIO_BYTES,
            self.const.CONF_ALLOW_OTA_ON_BATTERY,
            self.const.CONF_MIN_BATTERY_FOR_OTA,
        }

        self.assertTrue(advanced_only.isdisjoint(basic_keys))
        self.assertTrue(advanced_only.issubset(advanced_keys))

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
        self.assertEqual(data[self.const.CONF_MIN_BATTERY_FOR_OTA], 55)


if __name__ == "__main__":
    unittest.main()
