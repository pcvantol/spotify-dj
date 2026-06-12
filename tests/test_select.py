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

    def test_setup_entry_skips_device_selects_for_app_clients(self) -> None:
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

                asyncio.run(self.select.async_setup_entry(hass, entry, added.extend))

                self.assertEqual(
                    [entity._attr_translation_key for entity in added],
                    ["sound_output", "repeat_state"],
                )

    def test_setup_entry_adds_device_selects_for_esp32(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={"client_type": "esp32"},
            device_status={"client_type": "esp32"},
            listeners=[],
        )
        hass = types.SimpleNamespace(data={"djconnect": {"entry-1": runtime}})
        entry = types.SimpleNamespace(entry_id="entry-1")
        added = []

        asyncio.run(self.select.async_setup_entry(hass, entry, added.extend))

        self.assertEqual(
            [entity._attr_translation_key for entity in added],
            [
                "sound_output",
                "repeat_state",
                "language",
                "turn_off_after",
                "theme",
                "log_level",
            ],
        )

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

    def test_sound_output_uses_output_alias_and_available_outputs(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={
                "output": "Living room",
                "available_outputs": [
                    {"id": "dev-1", "name": "Living room"},
                    {"id": "dev-2", "name": "Kitchen"},
                ],
            },
            last_playback={},
            listeners=[],
        )
        sound_output = self.select.DJConnectCommandSelect(
            runtime,
            object(),
            "sound_output",
            "sound_output",
            "set_output",
            [],
        )

        self.assertEqual(sound_output.options, ["Living room", "Kitchen"])
        self.assertEqual(sound_output.current_option, "Living room")

    def test_sound_output_uses_devices_aliases(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={
                "devices": {"items": [{"id": "dev-1", "name": "Living room"}]},
                "sound_output": "Living room",
            },
            last_playback={},
            listeners=[],
        )
        sound_output = self.select.DJConnectCommandSelect(
            runtime,
            object(),
            "sound_output",
            "sound_output",
            "set_output",
            [],
        )

        self.assertEqual(sound_output.options, ["Living room"])
        self.assertEqual(
            self.select._output_id_from_option(runtime.device_status, "Living room"),
            "dev-1",
        )

    def test_sound_output_update_fetches_spotify_devices(self) -> None:
        calls = []
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={},
            last_playback={},
            listeners=[],
            update=lambda **kwargs: calls.append(("update", kwargs)),
        )
        sound_output = self.select.DJConnectCommandSelect(
            runtime,
            object(),
            "sound_output",
            "sound_output",
            "set_output",
            [],
        )

        async def fake_handler(hass, runtime_arg, command, value=None, *, play=None):
            calls.append((command, value, play))
            runtime_arg.device_status["available_outputs"] = [
                {"id": "dev-1", "name": "Living room"}
            ]
            return {"success": True, "devices": runtime_arg.device_status["available_outputs"]}

        original = self.select.handle_spotify_command
        self.select.handle_spotify_command = fake_handler
        try:
            asyncio.run(sound_output.async_update())
        finally:
            self.select.handle_spotify_command = original

        self.assertIn(("devices", None, None), calls)
        self.assertEqual(sound_output.options, ["Living room"])

    def test_sound_output_prefers_playback_device_and_active_output(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={
                "available_outputs": [
                    {"id": "dev-1", "name": "Living room", "active": False},
                    {"id": "dev-2", "name": "Kitchen", "active": True},
                ],
            },
            last_playback={},
            listeners=[],
        )
        sound_output = self.select.DJConnectCommandSelect(
            runtime,
            object(),
            "sound_output",
            "sound_output",
            "set_output",
            [],
        )

        self.assertEqual(sound_output.current_option, "Kitchen")
        runtime.last_playback = {"device": {"id": "dev-1", "name": "Living room"}}
        self.assertEqual(sound_output.current_option, "Living room")

    def test_turn_off_after_select_uses_fixed_minute_options(self) -> None:
        calls = []

        async def async_device_command(hass, command, **kwargs):
            calls.append((command, kwargs))
            return {"success": True}

        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={"turn_off_after": 900000},
            listeners=[],
            async_device_command=async_device_command,
            update=lambda **kwargs: calls.append(("update", kwargs)),
        )
        turn_off_after = self.select.DJConnectCommandSelect(
            runtime,
            object(),
            "turn_off_after",
            "turn_off_after",
            "turn_off_after",
            self.select.TURN_OFF_AFTER_OPTIONS,
        )

        self.assertEqual(turn_off_after.options, ["5", "15", "30", "60"])
        self.assertEqual(turn_off_after.current_option, "15")
        asyncio.run(turn_off_after.async_select_option("30"))

        self.assertIn(("turn_off_after", {"value": 1800000}), calls)
        self.assertEqual(runtime.device_status["turn_off_after"], "30")

    def test_turn_off_after_select_rounds_to_closest_option(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={"turn_off_after_ms": 1200000},
            listeners=[],
        )
        turn_off_after = self.select.DJConnectCommandSelect(
            runtime,
            object(),
            "turn_off_after",
            "turn_off_after",
            "turn_off_after",
            self.select.TURN_OFF_AFTER_OPTIONS,
        )

        self.assertEqual(turn_off_after.current_option, "15")


if __name__ == "__main__":
    unittest.main()
