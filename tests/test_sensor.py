from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install_sensor_stubs() -> None:
    homeassistant = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = sys.modules.setdefault(
        "homeassistant.components",
        types.ModuleType("homeassistant.components"),
    )
    sensor = types.ModuleType("homeassistant.components.sensor")
    config_entries = types.ModuleType("homeassistant.config_entries")
    const = types.ModuleType("homeassistant.const")
    core = types.ModuleType("homeassistant.core")
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

    class SensorEntity:
        def async_write_ha_state(self):
            self.wrote_state = True

    sensor.SensorEntity = SensorEntity
    sensor.SensorDeviceClass = types.SimpleNamespace(BATTERY="battery", SIGNAL_STRENGTH="signal_strength")
    sensor.SensorStateClass = types.SimpleNamespace(MEASUREMENT="measurement")
    config_entries.ConfigEntry = object
    const.PERCENTAGE = "%"
    const.SIGNAL_STRENGTH_DECIBELS_MILLIWATT = "dBm"
    core.HomeAssistant = object
    core.callback = lambda func: func
    device_registry.DeviceInfo = dict
    entity_platform.AddEntitiesCallback = object
    components.sensor = sensor
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    homeassistant.components = components

    sys.modules["homeassistant.components.sensor"] = sensor
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.const"] = const
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform


class DJConnectSensorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_sensor_stubs()
        cls.sensor = importlib.import_module("custom_components.djconnect.sensor")

    def test_pairing_status_is_pending_until_device_confirms(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_token="device-token",
            device_status={},
            listeners=[],
        )
        entity = self.sensor.DJConnectPairingStatusSensor(runtime)

        self.assertEqual(entity.native_value, "pending")

        runtime.device_status["ha_pairing_status"] = "paired"
        self.assertEqual(entity.native_value, "paired")

    def test_screen_and_led_state_sensors_read_status_payload(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={"screen_state": "on", "led_state": "off"},
            listeners=[],
        )

        screen = self.sensor.DJConnectScreenStateSensor(runtime)
        led = self.sensor.DJConnectLedStateSensor(runtime)

        self.assertEqual(screen.native_value, "on")
        self.assertEqual(led.native_value, "off")


if __name__ == "__main__":
    unittest.main()
