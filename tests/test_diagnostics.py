from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_diagnostics_stubs() -> None:
    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    core = sys.modules.setdefault(
        "homeassistant.core",
        types.ModuleType("homeassistant.core"),
    )
    config_entries = sys.modules.setdefault(
        "homeassistant.config_entries",
        types.ModuleType("homeassistant.config_entries"),
    )
    core.HomeAssistant = object
    config_entries.ConfigEntry = object

    package = types.ModuleType("custom_components.spotify_dj")
    package.__path__ = [str(ROOT / "custom_components" / "spotify_dj")]
    sys.modules.setdefault("custom_components.spotify_dj", package)


class DiagnosticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_diagnostics_stubs()
        cls.diagnostics = importlib.import_module("custom_components.spotify_dj.diagnostics")

    def test_redact_hides_token_password_and_secret_aliases(self) -> None:
        data = {
            "device_token": "device-secret",
            "refresh_token": "refresh-secret",
            "spotify_refresh_token": "spotify-secret",
            "mqtt_password": "mqtt-secret",
            "nested": {
                "password": "nested-secret",
                "client_id": "safe-client-id",
            },
        }

        redacted = self.diagnostics._redact(data)

        self.assertEqual(redacted["device_token"], "REDACTED")
        self.assertEqual(redacted["refresh_token"], "REDACTED")
        self.assertEqual(redacted["spotify_refresh_token"], "REDACTED")
        self.assertEqual(redacted["mqtt_password"], "REDACTED")
        self.assertEqual(redacted["nested"]["password"], "REDACTED")
        self.assertEqual(redacted["nested"]["client_id"], "safe-client-id")

    def test_diagnostics_include_legal_metadata_and_redact_secrets(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            title="SpotifyDJ",
            data={
                "spotify_refresh_token": "refresh-secret",
                "spotify_scopes": "user-read-playback-state user-modify-playback-state",
            },
            options={"mqtt_password": "mqtt-secret"},
        )
        hass = types.SimpleNamespace(data={"spotify_dj": {"entry-1": None}})

        result = asyncio.run(
            self.diagnostics.async_get_config_entry_diagnostics(hass, entry)
        )

        self.assertEqual(
            result["legal"]["copyright"],
            "Copyright (c) 2026 Peter van Tol. All rights reserved.",
        )
        self.assertEqual(
            result["legal"]["spotify_trademark"],
            "Spotify is a trademark of Spotify AB.",
        )
        self.assertEqual(
            result["legal"]["affiliation"],
            "SpotifyDJ is not affiliated with, endorsed by, or sponsored by Spotify AB.",
        )
        self.assertIn(
            "playlist-read-private",
            result["spotify_oauth"]["missing_scopes"],
        )
        self.assertTrue(result["spotify_oauth"]["reauthorization_required"])
        self.assertEqual(result["entry"]["data"]["spotify_refresh_token"], "REDACTED")
        self.assertEqual(result["entry"]["options"]["mqtt_password"], "REDACTED")


if __name__ == "__main__":
    unittest.main()
