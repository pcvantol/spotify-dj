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
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    awesomeversion = sys.modules.setdefault(
        "awesomeversion",
        types.ModuleType("awesomeversion"),
    )

    class UpdateEntity:
        def async_write_ha_state(self):
            self.write_count = getattr(self, "write_count", 0) + 1
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

    class AwesomeVersion:
        def __init__(self, value):
            self.parts = tuple(int(part) for part in str(value).split("."))

        def __gt__(self, other):
            return self.parts > other.parts

    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.ClientResponseError = ClientResponseError
    update.UpdateEntity = UpdateEntity
    update.UpdateEntityFeature = Feature
    config_entries.ConfigEntry = object
    core.HomeAssistant = object
    device_registry.DeviceInfo = dict
    entity_platform.AddEntitiesCallback = object
    aiohttp_client.async_get_clientsession = lambda hass: None
    awesomeversion.AwesomeVersion = AwesomeVersion
    components.update = update
    helpers.aiohttp_client = aiohttp_client
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    homeassistant.components = components

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules["custom_components.djconnect"] = package

    sys.modules["homeassistant.components.update"] = update
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client
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
            version="3.0.6",
            title="DJConnect v3.0.6",
            body="Release notes",
            firmware_url="https://example.test/djconnect-lilygo-t-embed-s3-v3.0.6.bin",
            firmware_asset="djconnect-lilygo-t-embed-s3-v3.0.6.bin",
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
        self.assertEqual(entity.latest_version, "3.0.6")

    def test_firmware_update_entity_does_not_poll(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={},
            ota_in_progress=False,
            ota_last_error=None,
            listeners=[],
        )
        entity = self.update.DJConnectFirmwareUpdate(runtime, object())

        self.assertFalse(entity._attr_should_poll)

    def test_firmware_release_config_uses_device_status_model(self) -> None:
        runtime = types.SimpleNamespace(
            config={},
            device_status={"model": "esp32_s3_box3"},
        )

        config = self.update._firmware_release_config(runtime)

        self.assertEqual(config["firmware_repo"], "pcvantol/djconnect-firmware")
        self.assertEqual(config["firmware_channel"], "stable")
        self.assertEqual(config["firmware_device"], "esp32-s3-box-3")

    def test_firmware_release_config_defaults_to_lilygo(self) -> None:
        runtime = types.SimpleNamespace(config={}, device_status={})

        config = self.update._firmware_release_config(runtime)

        self.assertEqual(config["firmware_device"], "lilygo-t-embed-s3")

    def test_firmware_release_config_uses_beta_channel_option(self) -> None:
        runtime = types.SimpleNamespace(
            config={"firmware_channel": "beta"},
            device_status={},
        )

        config = self.update._firmware_release_config(runtime)

        self.assertEqual(config["firmware_channel"], "beta")

    def test_runtime_updates_only_write_when_firmware_state_changes(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            config={},
            device_status={"firmware": "3.0.6"},
            ota_in_progress=False,
            ota_last_error=None,
            listeners=[],
        )
        entity = self.update.DJConnectFirmwareUpdate(runtime, object())

        entity._handle_runtime_update()
        entity._handle_runtime_update()
        runtime.device_status["firmware"] = "3.0.7"
        entity._handle_runtime_update()

        self.assertEqual(entity.write_count, 2)


if __name__ == "__main__":
    unittest.main()
