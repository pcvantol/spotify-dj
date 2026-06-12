from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_number_stubs() -> None:
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class NumberEntity:
        pass

    aiohttp.ClientTimeout = ClientTimeout
    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = sys.modules.setdefault(
        "homeassistant.components",
        types.ModuleType("homeassistant.components"),
    )
    number = sys.modules.setdefault(
        "homeassistant.components.number",
        types.ModuleType("homeassistant.components.number"),
    )
    config_entries = sys.modules.setdefault(
        "homeassistant.config_entries",
        types.ModuleType("homeassistant.config_entries"),
    )
    const = sys.modules.setdefault("homeassistant.const", types.ModuleType("homeassistant.const"))
    core = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
    helpers = sys.modules.setdefault(
        "homeassistant.helpers",
        types.ModuleType("homeassistant.helpers"),
    )
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )
    device_registry = sys.modules.setdefault(
        "homeassistant.helpers.device_registry",
        types.ModuleType("homeassistant.helpers.device_registry"),
    )
    entity_platform = sys.modules.setdefault(
        "homeassistant.helpers.entity_platform",
        types.ModuleType("homeassistant.helpers.entity_platform"),
    )

    components.number = number
    number.NumberEntity = NumberEntity
    config_entries.ConfigEntry = object
    const.PERCENTAGE = "%"
    core.HomeAssistant = object
    core.callback = lambda func: func
    aiohttp_client.async_get_clientsession = lambda hass: None
    device_registry.DeviceInfo = dict
    entity_platform.AddEntitiesCallback = object
    helpers.aiohttp_client = aiohttp_client
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules["custom_components.djconnect"] = package


class NumberTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_number_stubs()
        cls.number = importlib.import_module("custom_components.djconnect.number")

    def test_negative_volume_status_is_unknown(self) -> None:
        self.assertEqual(self.number._volume_value({"volume": -1}), -1.0)

        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={"volume": -1},
            listeners=[],
        )
        entity = self.number.DJConnectVolumeNumber(runtime, object())

        self.assertIsNone(entity.native_value)

    def test_volume_status_is_clamped_to_range(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={"volume": 90},
            listeners=[],
        )
        entity = self.number.DJConnectVolumeNumber(runtime, object())

        self.assertEqual(entity.native_value, 60.0)

    def test_device_setting_numbers_read_firmware_aliases(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={
                "screen_brightness_percent": 73,
                "volume": 44,
                "screen_off_timeout_ms": 45000,
            },
            listeners=[],
        )

        brightness = self.number.DJConnectCommandNumber(
            runtime,
            object(),
            "screen_brightness",
            "brightness",
            "screen_brightness",
            "value",
            0,
            100,
            "%",
        )
        speaker = self.number.DJConnectCommandNumber(
            runtime,
            object(),
            "speaker_volume",
            "speaker_volume",
            "speaker_volume",
            "value",
            0,
            100,
            "%",
        )
        screen_timeout = self.number.DJConnectCommandNumber(
            runtime,
            object(),
            "screen_timeout",
            "screen_timeout",
            "screen_dim_timeout",
            "value",
            0,
            600,
            "s",
            value_multiplier=1000,
        )

        self.assertEqual(brightness.native_value, 73)
        self.assertEqual(speaker.native_value, 44)
        self.assertEqual(screen_timeout.native_value, 45)

    def test_setup_entry_adds_only_playback_volume_for_app_clients(self) -> None:
        for client_type in ("ios", "macos", "raspberry_pi"):
            with self.subTest(client_type=client_type):
                runtime = types.SimpleNamespace(
                    entry=types.SimpleNamespace(entry_id="entry-1"),
                    config={"client_type": client_type},
                    device_status={"client_type": client_type},
                    listeners=[],
                )
                hass = types.SimpleNamespace(data={"djconnect": {"entry-1": runtime}})
                entry = types.SimpleNamespace(entry_id="entry-1")
                added = []

                asyncio.run(self.number.async_setup_entry(hass, entry, added.extend))

                self.assertEqual([entity._attr_translation_key for entity in added], ["volume"])

    def test_setup_entry_adds_device_numbers_for_esp32(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={"client_type": "esp32"},
            device_status={"client_type": "esp32"},
            listeners=[],
        )
        hass = types.SimpleNamespace(data={"djconnect": {"entry-1": runtime}})
        entry = types.SimpleNamespace(entry_id="entry-1")
        added = []

        asyncio.run(self.number.async_setup_entry(hass, entry, added.extend))

        self.assertEqual(
            [entity._attr_translation_key for entity in added],
            ["volume", "brightness", "screen_timeout", "speaker_volume"],
        )


if __name__ == "__main__":
    unittest.main()
