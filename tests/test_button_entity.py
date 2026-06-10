from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def install_button_stubs() -> None:
    homeassistant = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = sys.modules.setdefault("homeassistant.components", types.ModuleType("homeassistant.components"))
    button = types.ModuleType("homeassistant.components.button")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

    class ButtonEntity:
        pass

    button.ButtonEntity = ButtonEntity
    config_entries.ConfigEntry = object
    core.HomeAssistant = object
    device_registry.DeviceInfo = dict
    entity_platform.AddEntitiesCallback = object
    components.button = button
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    homeassistant.components = components

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    package.DEFAULT_TEST_TTS_TEXT = "test"

    async def async_speak_dj_test(*args, **kwargs):
        return None

    package.async_speak_dj_test = async_speak_dj_test
    sys.modules["custom_components.djconnect"] = package
    spotify_backend = types.ModuleType("custom_components.djconnect.spotify_backend")

    class SpotifyBackendError(Exception):
        pass

    async def handle_spotify_command(*args, **kwargs):
        return {}

    spotify_backend.SpotifyBackendError = SpotifyBackendError
    spotify_backend.handle_spotify_command = handle_spotify_command
    sys.modules["custom_components.djconnect.spotify_backend"] = spotify_backend
    sys.modules["homeassistant.components.button"] = button
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform


class DJConnectButtonEntityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_button_stubs()
        cls.button = importlib.import_module("custom_components.djconnect.button")

    @classmethod
    def tearDownClass(cls) -> None:
        for module in (
            "custom_components.djconnect.button",
            "custom_components.djconnect.spotify_backend",
            "custom_components.djconnect.entity_ids",
            "custom_components.djconnect.const",
            "custom_components.djconnect",
        ):
            sys.modules.pop(module, None)

    def test_reboot_button_is_skipped_for_app_clients(self) -> None:
        added = []
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            client_type=lambda: "macos",
        )
        hass = types.SimpleNamespace(data={"djconnect": {"entry-1": runtime}})
        entry = types.SimpleNamespace(entry_id="entry-1")

        asyncio.run(
            self.button.async_setup_entry(hass, entry, lambda entities: added.extend(entities))
        )

        translation_keys = {entity._attr_translation_key for entity in added}
        self.assertNotIn("reboot_device", translation_keys)

    def test_reboot_button_is_added_for_esp32_clients(self) -> None:
        added = []
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            client_type=lambda: "esp32",
        )
        hass = types.SimpleNamespace(data={"djconnect": {"entry-1": runtime}})
        entry = types.SimpleNamespace(entry_id="entry-1")

        asyncio.run(
            self.button.async_setup_entry(hass, entry, lambda entities: added.extend(entities))
        )

        translation_keys = {entity._attr_translation_key for entity in added}
        self.assertIn("reboot_device", translation_keys)


if __name__ == "__main__":
    unittest.main()
