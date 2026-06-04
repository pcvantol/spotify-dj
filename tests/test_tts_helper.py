from __future__ import annotations

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
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )
    typing = sys.modules.setdefault(
        "homeassistant.helpers.typing",
        types.ModuleType("homeassistant.helpers.typing"),
    )

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    aiohttp.ClientTimeout = ClientTimeout
    config_entries.ConfigEntry = object
    core.HomeAssistant = object
    core.ServiceCall = object
    aiohttp_client.async_get_clientsession = lambda hass: None
    typing.ConfigType = dict


class TtsHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_integration_stubs()
        sys.modules.pop("custom_components.spotify_dj", None)
        cls.integration = importlib.import_module("custom_components.spotify_dj")
        cls.const = importlib.import_module("custom_components.spotify_dj.const")

    def test_tts_service_data_uses_configured_player_and_defaults(self) -> None:
        runtime = types.SimpleNamespace(
            config={
                self.const.CONF_SPOTIFY_PLAYER: "media_player.spotify",
            }
        )

        data = self.integration._tts_service_data(runtime, "Test tekst")

        self.assertEqual(data["entity_id"], self.const.DEFAULT_TTS_ENGINE)
        self.assertEqual(data["media_player_entity_id"], "media_player.spotify")
        self.assertEqual(data["message"], "Test tekst")
        self.assertEqual(data["language"], self.const.DEFAULT_TTS_LANGUAGE)

    def test_tts_service_data_requires_player(self) -> None:
        runtime = types.SimpleNamespace(config={})

        with self.assertRaisesRegex(RuntimeError, "Spotify/media_player"):
            self.integration._tts_service_data(runtime, "Test tekst")

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


if __name__ == "__main__":
    unittest.main()
