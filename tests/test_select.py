from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install_select_stubs() -> None:
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = sys.modules.setdefault("homeassistant.components", types.ModuleType("homeassistant.components"))
    select = types.ModuleType("homeassistant.components.select")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

    class SelectEntity:
        def async_write_ha_state(self):
            self.wrote_state = True

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    aiohttp.ClientTimeout = ClientTimeout
    select.SelectEntity = SelectEntity
    config_entries.ConfigEntry = object
    core.HomeAssistant = object
    core.callback = lambda func: func
    device_registry.DeviceInfo = dict
    entity_platform.AddEntitiesCallback = object
    components.select = select
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    helpers.aiohttp_client = aiohttp_client
    aiohttp_client.async_get_clientsession = lambda hass: None

    sys.modules["homeassistant.components.select"] = select
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules.setdefault("custom_components.djconnect", package)


class DJConnectSelectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_select_stubs()
        cls.select = importlib.import_module("custom_components.djconnect.select")

    def test_theme_and_log_level_have_initial_defaults(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={"device_language": "nl"},
            device_status={},
            listeners=[],
        )

        theme = self.select.DJConnectCommandSelect(runtime, object(), "theme", "theme", "theme", ["light", "dark", "auto"])
        log_level = self.select.DJConnectCommandSelect(runtime, object(), "log_level", "log_level", "log_level", ["debug", "info", "warning", "error"])
        language = self.select.DJConnectCommandSelect(runtime, object(), "language", "language", "language", ["en", "nl"])

        self.assertEqual(theme.current_option, "auto")
        self.assertEqual(log_level.current_option, "info")
        self.assertEqual(language.current_option, "nl")

    def test_repeat_select_uses_spotify_backend_command(self) -> None:
        calls = []
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={},
            listeners=[],
            update=lambda **kwargs: calls.append(("update", kwargs)),
        )
        repeat = self.select.DJConnectCommandSelect(
            runtime,
            object(),
            "repeat_state",
            "repeat_state",
            "set_repeat",
            ["off", "track", "context"],
        )

        async def fake_handler(hass, runtime_arg, command, value=None, *, play=None):
            calls.append((command, value, play))
            return {"success": True}

        original = self.select.handle_spotify_command
        self.select.handle_spotify_command = fake_handler
        try:
            asyncio.run(repeat.async_select_option("track"))
        finally:
            self.select.handle_spotify_command = original

        self.assertIn(("set_repeat", "track", None), calls)
        self.assertEqual(runtime.device_status["repeat_state"], "track")


if __name__ == "__main__":
    unittest.main()
