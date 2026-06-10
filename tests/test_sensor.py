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
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

    class SensorEntity:
        def async_write_ha_state(self):
            self.write_count = getattr(self, "write_count", 0) + 1
            self.wrote_state = True

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    aiohttp.ClientTimeout = ClientTimeout
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
    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules["custom_components.djconnect"] = package

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

    def test_last_track_sensor_reads_backend_and_device_aliases(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={"last_track": "Device Track"},
            last_playback={"track_name": "Backend Track"},
            last_resolved_media={},
            listeners=[],
        )
        entity = self.sensor.DJConnectLastTrackSensor(runtime)

        self.assertEqual(entity.native_value, "Backend Track")
        runtime.last_playback = {}
        self.assertEqual(entity.native_value, "Device Track")
        runtime.device_status = {"track": "Firmware Track"}
        self.assertEqual(entity.native_value, "Firmware Track")

    def test_last_track_sensor_keeps_cached_value_when_runtime_becomes_empty(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={"last_track": "Alive"},
            last_playback={},
            last_resolved_media={},
            listeners=[],
        )
        entity = self.sensor.DJConnectLastTrackSensor(runtime)

        self.assertTrue(entity.available)
        self.assertEqual(entity.native_value, "Alive")
        runtime.device_status = {}
        runtime.last_playback = {}
        runtime.last_resolved_media = {}
        self.assertEqual(entity.native_value, "Alive")

        runtime.last_resolved_media = {"artist": "Pearl Jam"}
        self.assertEqual(entity.native_value, "Pearl Jam")

    def test_last_track_sensor_is_push_only_and_writes_only_on_change(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={"last_track": "Alive"},
            last_playback={},
            last_resolved_media={},
            listeners=[],
        )
        entity = self.sensor.DJConnectLastTrackSensor(runtime)

        self.assertFalse(entity._attr_should_poll)

        entity._handle_runtime_update()
        entity._handle_runtime_update()
        runtime.device_status["last_track"] = "Black"
        entity._handle_runtime_update()

        self.assertEqual(entity.write_count, 2)

    def test_last_command_sensor_reads_runtime_last_text(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            last_text="Speel Pearl Jam",
            last_stt_text="ik wil pearl jam starten",
            last_dj_text="Daar is Pearl Jam",
            last_intent={"action": "play"},
            last_spotify_search={
                "query": "ik wil pearl jam starten",
                "selected": {"title": "Alive", "artist": "Pearl Jam"},
            },
            last_resolved_media={"title": "Alive", "artist": "Pearl Jam"},
            listeners=[],
        )
        entity = self.sensor.DJConnectLastTextSensor(runtime)

        self.assertTrue(entity.available)
        self.assertEqual(entity.native_value, "Daar is Pearl Jam")
        self.assertEqual(entity.extra_state_attributes["last_text"], "Speel Pearl Jam")
        self.assertEqual(entity.extra_state_attributes["last_dj_text"], "Daar is Pearl Jam")
        self.assertEqual(entity.extra_state_attributes["last_stt_text"], "ik wil pearl jam starten")
        self.assertEqual(entity.extra_state_attributes["last_intent"], {"action": "play"})
        self.assertEqual(
            entity.extra_state_attributes["last_spotify_search"]["selected"]["title"],
            "Alive",
        )
        self.assertEqual(
            entity.extra_state_attributes["last_resolved_media"]["artist"],
            "Pearl Jam",
        )

    def test_last_command_sensor_keeps_cached_value_when_runtime_becomes_empty(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            last_text="ik wil pearl jam starten",
            last_stt_text="ik wil pearl jam starten",
            last_dj_text="Daar is Pearl Jam",
            last_intent=None,
            last_spotify_search=None,
            last_resolved_media=None,
            device_status={},
            listeners=[],
        )
        entity = self.sensor.DJConnectLastTextSensor(runtime)

        self.assertEqual(entity.native_value, "Daar is Pearl Jam")
        runtime.last_text = None
        runtime.last_stt_text = None
        runtime.last_dj_text = None
        self.assertEqual(entity.native_value, "Daar is Pearl Jam")
        self.assertEqual(
            entity.extra_state_attributes["last_stt_text"],
            "Daar is Pearl Jam",
        )

    def test_last_command_sensor_is_push_only_and_writes_only_on_change(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            last_text="ik wil pearl jam starten",
            last_stt_text="ik wil pearl jam starten",
            last_dj_text="Daar is Pearl Jam",
            last_intent=None,
            last_spotify_search=None,
            last_resolved_media=None,
            device_status={},
            listeners=[],
        )
        entity = self.sensor.DJConnectLastTextSensor(runtime)

        self.assertFalse(entity._attr_should_poll)

        entity._handle_runtime_update()
        entity._handle_runtime_update()
        runtime.last_dj_text = "Pearl Jam staat klaar."
        entity._handle_runtime_update()

        self.assertEqual(entity.write_count, 2)

    def test_last_command_sensor_restores_persisted_dj_response_text(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            last_text=None,
            last_stt_text=None,
            last_dj_text=None,
            last_intent=None,
            last_spotify_search=None,
            last_resolved_media=None,
            device_status={
                "last_command": "ik wil pearl jam starten",
                "last_dj_text": "Daar is Pearl Jam",
            },
            listeners=[],
        )
        entity = self.sensor.DJConnectLastTextSensor(runtime)

        self.assertEqual(entity.native_value, "Daar is Pearl Jam")
        self.assertEqual(entity.extra_state_attributes["last_dj_text"], "Daar is Pearl Jam")

    def test_last_command_sensor_skips_assist_prompt_leak_error(self) -> None:
        leaked = (
            "Sorry, ik kan Gebruik deze DJ response prompt als stijl-/inhoudsinstructie "
            "Maak een korte gesproken DJ-aankondiging in het Nederlands Media type artist "
            "artiest Red Hot Chili Peppers Antwoord alleen met de tekst die uitgesproken "
            "moet worden Geen JSON geen uitleg geen URI niet vinden"
        )
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            last_text="zet red hot chili peppers op",
            last_stt_text="zet red hot chili peppers op",
            last_dj_text=leaked,
            last_intent=None,
            last_spotify_search=None,
            last_resolved_media=None,
            device_status={},
            listeners=[],
        )
        entity = self.sensor.DJConnectLastTextSensor(runtime)

        self.assertEqual(entity.native_value, "zet red hot chili peppers op")
        self.assertEqual(entity.extra_state_attributes["full_value"], leaked)
        self.assertTrue(entity.extra_state_attributes["state_prompt_leak_ignored"])
        self.assertEqual(entity.extra_state_attributes["last_dj_text"], leaked)

    def test_last_command_sensor_truncates_long_state_text(self) -> None:
        long_text = "x" * 300
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            last_text=None,
            last_stt_text=None,
            last_dj_text=long_text,
            last_intent=None,
            last_spotify_search=None,
            last_resolved_media=None,
            device_status={},
            listeners=[],
        )
        entity = self.sensor.DJConnectLastTextSensor(runtime)

        self.assertEqual(len(entity.native_value), 255)
        self.assertTrue(entity.native_value.endswith("…"))
        self.assertEqual(entity.extra_state_attributes["full_value"], long_text)
        self.assertTrue(entity.extra_state_attributes["state_truncated"])

    def test_status_sensor_exposes_voice_and_spotify_debug_attributes(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            last_error=None,
            last_stt_text="ik wil pearl jam starten",
            last_spotify_search={"query": "pearl jam", "returned": 1},
            last_resolved_media={"title": "Alive"},
            last_dj_text="Daar is Pearl Jam",
            last_dj_response_debug={"fallback_used": True, "block_reason": "test"},
            last_playback={},
            device_status={},
            ota_in_progress=False,
            ota_last_error=None,
            listeners=[],
        )
        entity = self.sensor.DJConnectStatusSensor(runtime)

        attrs = entity.extra_state_attributes
        self.assertEqual(attrs["last_stt_text"], "ik wil pearl jam starten")
        self.assertEqual(attrs["last_spotify_search"]["query"], "pearl jam")
        self.assertEqual(attrs["last_resolved_media"]["title"], "Alive")
        self.assertTrue(attrs["last_dj_response_debug"]["fallback_used"])

    def test_queue_sensor_reads_dict_items_and_context(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={
                "queue": {
                    "items": [{"title": "Song"}],
                    "context": {"uri": "spotify:playlist:abc"},
                    "currently_playing": {"title": "Current"},
                }
            },
            last_playback={},
            listeners=[],
        )
        entity = self.sensor.DJConnectQueueSensor(runtime)

        self.assertEqual(entity.native_value, 1)
        self.assertEqual(entity.extra_state_attributes["items"], [{"title": "Song"}])
        self.assertEqual(
            entity.extra_state_attributes["context"],
            {"uri": "spotify:playlist:abc"},
        )
        self.assertEqual(
            entity.extra_state_attributes["currently_playing"],
            {"title": "Current"},
        )

    def test_queue_sensor_falls_back_to_playback_context(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={},
            last_playback={"queue_context": "spotify:playlist:def"},
            listeners=[],
        )
        entity = self.sensor.DJConnectQueueSensor(runtime)

        self.assertEqual(entity.native_value, 0)
        self.assertEqual(entity.extra_state_attributes["context"], "spotify:playlist:def")


if __name__ == "__main__":
    unittest.main()
