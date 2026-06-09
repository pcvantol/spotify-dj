from __future__ import annotations

import importlib
import asyncio
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_ble_stubs() -> None:
    homeassistant = sys.modules.setdefault(
        "homeassistant",
        types.ModuleType("homeassistant"),
    )
    core = sys.modules.setdefault(
        "homeassistant.core",
        types.ModuleType("homeassistant.core"),
    )
    core.HomeAssistant = object
    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules.setdefault("custom_components.djconnect", package)
    homeassistant.core = core


class BleHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_ble_stubs()
        cls.ble = importlib.import_module("custom_components.djconnect.ble")

    def test_wifi_payload_is_compact_utf8_json(self) -> None:
        payload = self.ble.wifi_payload("Thuis", "geheim")

        self.assertEqual(payload, b'{"ssid":"Thuis","password":"geheim"}')

    def test_parse_status_accepts_utf8_json(self) -> None:
        status = self.ble.parse_status(
            b'{"state":"success","message":"WiFi saved, restarting"}'
        )

        self.assertEqual(status["state"], "success")
        self.assertEqual(status["message"], "WiFi saved, restarting")

    def test_parse_status_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Invalid BLE status JSON"):
            self.ble.parse_status(b"not json")

    def test_provision_wifi_status_timeout_returns_submitted(self) -> None:
        class Client:
            disconnected = False

            async def write_gatt_char(self, uuid, payload, response=True):
                self.uuid = uuid
                self.payload = payload

            async def read_gatt_char(self, uuid):
                await asyncio.sleep(0.02)

            async def disconnect(self):
                self.disconnected = True

        client = Client()

        async def connect(hass, address):
            return client

        original_connect = self.ble._connect_client
        original_timeout = self.ble.BLE_STATUS_TIMEOUT
        self.ble._connect_client = connect
        self.ble.BLE_STATUS_TIMEOUT = 0.001
        try:
            status = asyncio.run(
                self.ble.async_provision_wifi(object(), "AA:BB", "Thuis", "geheim")
            )
        finally:
            self.ble._connect_client = original_connect
            self.ble.BLE_STATUS_TIMEOUT = original_timeout

        self.assertEqual(status["state"], "submitted")
        self.assertTrue(client.disconnected)


if __name__ == "__main__":
    unittest.main()
