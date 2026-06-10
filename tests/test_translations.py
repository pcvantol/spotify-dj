from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "custom_components" / "djconnect" / "translations"
INTEGRATION = ROOT / "custom_components" / "djconnect"
DOCS = [
    ROOT / "README.md",
    ROOT / "CHANGELOG.md",
    ROOT / "HANDOFF.md",
    ROOT / "TODO.md",
    ROOT / "ISSUES.md",
    ROOT / "ESP_SYNC_PROMPT.md",
]

CONFIG_FLOW_ERROR_KEYS = {
    "missing_pair_code",
    "invalid_pair_code",
    "spotify_client_id_required",
    "external_url_required",
    "external_url_https_required",
    "external_url_invalid",
    "oauth_setup_failed",
    "oauth_not_completed",
    "oauth_failed",
    "ble_device_required",
    "wifi_ssid_required",
    "ble_wifi_failed",
    "repair_pairing_failed",
}

BLE_WIFI_DATA_KEYS = {
    "ble_action",
    "ble_address",
    "wifi_ssid",
    "wifi_password",
}

VOICE_OPTION_DATA_KEYS = {
    "assist_pipeline_id",
    "stt_engine",
    "dj_response_enabled",
    "firmware_channel",
    "dj_response_ttl_seconds",
    "allow_ota_on_battery",
    "show_advanced_options",
    "options_action",
}

ENTITY_TRANSLATION_KEYS = {
    ("sensor", "status"),
    ("sensor", "last_command"),
    ("sensor", "battery"),
    ("sensor", "wifi_rssi"),
    ("sensor", "firmware_version"),
    ("sensor", "last_track"),
    ("sensor", "spotify_status"),
    ("sensor", "ha_pairing_status"),
    ("sensor", "sound_output"),
    ("sensor", "playback_available"),
    ("sensor", "queue"),
    ("sensor", "playlists"),
    ("sensor", "outputs"),
    ("sensor", "screen_state"),
    ("sensor", "led_state"),
    ("button", "test_dj_response"),
    ("button", "next_track"),
    ("button", "previous_track"),
    ("button", "play_pause"),
    ("button", "refresh_device_info"),
    ("button", "refresh_up_next"),
    ("button", "reboot_device"),
    ("number", "volume"),
    ("number", "brightness"),
    ("number", "screen_timeout"),
    ("number", "speaker_volume"),
    ("select", "sound_output"),
    ("select", "repeat_state"),
    ("select", "language"),
    ("select", "turn_off_after"),
    ("select", "theme"),
    ("select", "log_level"),
    ("switch", "shuffle"),
    ("update", "firmware"),
    ("media_player", "playback_proxy"),
}


class TranslationTest(unittest.TestCase):
    def test_translation_files_cover_base_strings_schema(self) -> None:
        base = _leaf_paths(json.loads((INTEGRATION / "strings.json").read_text()))
        for language in ("en", "nl"):
            with self.subTest(language=language):
                data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
                missing = base - _leaf_paths(data)
                self.assertFalse(
                    missing,
                    f"Missing {language} schema translations: {sorted(missing)}",
                )

    def test_config_flow_error_keys_are_translated(self) -> None:
        for language in ("en", "nl"):
            with self.subTest(language=language):
                data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
                errors = data["config"]["error"]
                missing = CONFIG_FLOW_ERROR_KEYS - set(errors)
                self.assertFalse(missing, f"Missing {language} translations: {sorted(missing)}")

    def test_ble_wifi_fields_are_translated(self) -> None:
        for language in ("en", "nl"):
            with self.subTest(language=language):
                data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
                step = data["config"]["step"]["ble_wifi"]
                missing_labels = BLE_WIFI_DATA_KEYS - set(step["data"])
                missing_descriptions = BLE_WIFI_DATA_KEYS - set(step["data_description"])
                self.assertFalse(
                    missing_labels,
                    f"Missing {language} BLE labels: {sorted(missing_labels)}",
                )
                self.assertFalse(
                    missing_descriptions,
                    f"Missing {language} BLE descriptions: {sorted(missing_descriptions)}",
                )

    def test_options_flow_voice_fields_are_translated(self) -> None:
        base = json.loads((INTEGRATION / "strings.json").read_text())
        missing_base = VOICE_OPTION_DATA_KEYS - set(
            base["options"]["step"]["init"]["data"]
        )
        missing_base_descriptions = VOICE_OPTION_DATA_KEYS - set(
            base["options"]["step"]["init"]["data_description"]
        )
        self.assertFalse(missing_base, f"Missing base option labels: {sorted(missing_base)}")
        self.assertFalse(
            missing_base_descriptions,
            f"Missing base option descriptions: {sorted(missing_base_descriptions)}",
        )
        for language in ("en", "nl"):
            with self.subTest(language=language):
                data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
                step = data["options"]["step"]["init"]
                missing_labels = VOICE_OPTION_DATA_KEYS - set(step["data"])
                missing_descriptions = VOICE_OPTION_DATA_KEYS - set(
                    step["data_description"]
                )
                self.assertFalse(
                    missing_labels,
                    f"Missing {language} option labels: {sorted(missing_labels)}",
                )
                self.assertFalse(
                    missing_descriptions,
                    f"Missing {language} option descriptions: {sorted(missing_descriptions)}",
                )

    def test_entity_translation_keys_are_translated(self) -> None:
        for language in ("en", "nl"):
            with self.subTest(language=language):
                data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
                entity = data["entity"]
                missing = [
                    f"{platform}.{key}"
                    for platform, key in ENTITY_TRANSLATION_KEYS
                    if key not in entity.get(platform, {})
                ]
                self.assertFalse(missing, f"Missing {language} entity translations: {missing}")

    def test_entities_use_translation_keys(self) -> None:
        for filename in (
            "sensor.py",
            "button.py",
            "number.py",
            "select.py",
            "switch.py",
            "update.py",
            "media_player.py",
        ):
            with self.subTest(filename=filename):
                text = (INTEGRATION / filename).read_text()
                self.assertIn("_attr_translation_key", text)
                self.assertNotIn("_attr_name =", text)

    def test_no_old_branding_in_user_facing_integration_files(self) -> None:
        checked_files = [
            *TRANSLATIONS.glob("*.json"),
            INTEGRATION / "services.yaml",
            INTEGRATION / "strings.json",
        ]
        forbidden = ("openai", "open ai", "lilygo", "t-embed")
        for path in checked_files:
            with self.subTest(path=path.name):
                text = path.read_text().lower()
                hits = [word for word in forbidden if word in text]
                self.assertFalse(hits, f"{path} contains old branding: {hits}")

    def test_removed_message_bus_wording_stays_out_of_docs_and_ui(self) -> None:
        checked_files = [
            *DOCS,
            *TRANSLATIONS.glob("*.json"),
            INTEGRATION / "services.yaml",
            INTEGRATION / "strings.json",
        ]
        for path in checked_files:
            if not path.exists():
                continue
            with self.subTest(path=path.name):
                self.assertNotIn("m" + "qtt", path.read_text().lower())


def _leaf_paths(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return {prefix}
    paths: set[str] = set()
    for key, child in value.items():
        child_prefix = f"{prefix}.{key}" if prefix else str(key)
        paths.update(_leaf_paths(child, child_prefix))
    return paths


if __name__ == "__main__":
    unittest.main()
