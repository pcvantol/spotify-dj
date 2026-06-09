from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install_update_stubs() -> None:
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    homeassistant = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = sys.modules.setdefault("homeassistant.components", types.ModuleType("homeassistant.components"))
    update = types.ModuleType("homeassistant.components.update")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

    class UpdateEntity:
        def async_write_ha_state(self):
            self.wrote_state = True

    class Feature:
        INSTALL = 1
        SPECIFIC_VERSION = 2
        RELEASE_NOTES = 4

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class ClientResponseError(Exception):
        def __init__(self, *args, status=None, **kwargs):
            super().__init__("client response error")
            self.status = status

    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.ClientResponseError = ClientResponseError
    update.UpdateEntity = UpdateEntity
    update.UpdateEntityFeature = Feature
    config_entries.ConfigEntry = object
    core.HomeAssistant = object
    device_registry.DeviceInfo = dict
    entity_platform.AddEntitiesCallback = object
    components.update = update
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    homeassistant.components = components

    sys.modules["homeassistant.components.update"] = update
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform


class DJConnectUpdateEntityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_update_stubs()
        cls.update = importlib.import_module("custom_components.djconnect.update")

    def test_async_update_records_error_without_crashing(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={},
            ota_in_progress=False,
            ota_last_error=None,
            listeners=[],
        )
        entity = self.update.DJConnectFirmwareUpdate(runtime, object())

        async def fail(hass, config):
            raise RuntimeError("rate limit exceeded")

        original = self.update.fetch_latest_firmware_release
        self.update.fetch_latest_firmware_release = fail
        try:
            asyncio.run(entity.async_update())
        finally:
            self.update.fetch_latest_firmware_release = original

        self.assertEqual(entity.latest_version, "0.0.0")
        self.assertEqual(
            entity.extra_state_attributes["firmware_update_error"],
            "rate limit exceeded",
        )

    def test_async_update_throttles_successful_release_checks(self) -> None:
        github = importlib.import_module("custom_components.djconnect.github")
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={},
            ota_in_progress=False,
            ota_last_error=None,
            listeners=[],
        )
        entity = self.update.DJConnectFirmwareUpdate(runtime, object())
        release = github.FirmwareRelease(
            version="3.0.3",
            title="DJConnect v3.0.3",
            body="Release notes",
            firmware_url="https://example.test/djconnect-device-v3.0.3.bin",
            firmware_asset="djconnect-device-v3.0.3.bin",
            manifest_url="https://example.test/firmware_manifest.json",
            device="lilygo-t-embed-s3",
        )
        calls = 0

        async def fetch(hass, config):
            nonlocal calls
            calls += 1
            return release

        original = self.update.fetch_latest_firmware_release
        self.update.fetch_latest_firmware_release = fetch
        try:
            asyncio.run(entity.async_update())
            asyncio.run(entity.async_update())
            asyncio.run(entity.async_update(force=True))
        finally:
            self.update.fetch_latest_firmware_release = original

        self.assertEqual(calls, 2)
        self.assertEqual(entity.latest_version, "3.0.3")


if __name__ == "__main__":
    unittest.main()
