from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install_switch_stubs() -> None:
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = sys.modules.setdefault(
        "homeassistant.components",
        types.ModuleType("homeassistant.components"),
    )
    switch = types.ModuleType("homeassistant.components.switch")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

    class SwitchEntity:
        def async_write_ha_state(self):
            self.wrote_state = True

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    aiohttp.ClientTimeout = ClientTimeout
    switch.SwitchEntity = SwitchEntity
    config_entries.ConfigEntry = object
    core.HomeAssistant = object
    core.callback = lambda func: func
    device_registry.DeviceInfo = dict
    entity_platform.AddEntitiesCallback = object
    components.switch = switch
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    helpers.aiohttp_client = aiohttp_client
    aiohttp_client.async_get_clientsession = lambda hass: None

    sys.modules["homeassistant.components.switch"] = switch
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules.setdefault("custom_components.djconnect", package)


class DJConnectShuffleSwitchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_switch_stubs()
        cls.switch = importlib.import_module("custom_components.djconnect.switch")

    def test_shuffle_switch_uses_spotify_backend_command(self) -> None:
        calls = []
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={},
            last_playback={},
            listeners=[],
            update=lambda **kwargs: calls.append(("update", kwargs)),
        )
        entity = self.switch.DJConnectShuffleSwitch(runtime, object())

        async def fake_handler(hass, runtime_arg, command, value=None, *, play=None):
            calls.append((command, value, play))
            return {"success": True}

        original = self.switch.handle_spotify_command
        self.switch.handle_spotify_command = fake_handler
        try:
            asyncio.run(entity.async_turn_on())
            asyncio.run(entity.async_turn_off())
        finally:
            self.switch.handle_spotify_command = original

        self.assertIn(("set_shuffle", True, None), calls)
        self.assertIn(("set_shuffle", False, None), calls)
        self.assertFalse(entity.is_on)

    def test_shuffle_switch_reads_playback_state_first(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={"shuffle": False},
            last_playback={"shuffle": True},
            listeners=[],
        )
        entity = self.switch.DJConnectShuffleSwitch(runtime, object())

        self.assertTrue(entity.is_on)


if __name__ == "__main__":
    unittest.main()
