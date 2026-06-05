from __future__ import annotations

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

    package = types.ModuleType("custom_components.spotify_dj")
    package.__path__ = [str(ROOT / "custom_components" / "spotify_dj")]
    sys.modules["custom_components.spotify_dj"] = package


class NumberTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_number_stubs()
        cls.number = importlib.import_module("custom_components.spotify_dj.number")

    def test_negative_volume_status_is_unknown(self) -> None:
        self.assertEqual(self.number._volume_value({"volume": -1}), -1.0)

        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={"volume": -1},
            listeners=[],
        )
        entity = self.number.SpotifyDJVolumeNumber(runtime, object())

        self.assertIsNone(entity.native_value)

    def test_volume_status_is_clamped_to_range(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={"volume": 90},
            listeners=[],
        )
        entity = self.number.SpotifyDJVolumeNumber(runtime, object())

        self.assertEqual(entity.native_value, 60.0)


if __name__ == "__main__":
    unittest.main()
