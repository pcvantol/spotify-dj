from __future__ import annotations

import importlib
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
    package = types.ModuleType("custom_components.spotify_dj")
    package.__path__ = [str(ROOT / "custom_components" / "spotify_dj")]
    sys.modules.setdefault("custom_components.spotify_dj", package)
    homeassistant.core = core


class BleHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_ble_stubs()
        cls.ble = importlib.import_module("custom_components.spotify_dj.ble")

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


if __name__ == "__main__":
    unittest.main()
