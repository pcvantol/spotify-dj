from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_repairs_stubs() -> list[dict]:
    issues: list[dict] = []
    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    core = sys.modules.setdefault(
        "homeassistant.core",
        types.ModuleType("homeassistant.core"),
    )
    config_entries = sys.modules.setdefault(
        "homeassistant.config_entries",
        types.ModuleType("homeassistant.config_entries"),
    )
    helpers = sys.modules.setdefault(
        "homeassistant.helpers",
        types.ModuleType("homeassistant.helpers"),
    )
    issue_registry = types.ModuleType("homeassistant.helpers.issue_registry")

    class IssueSeverity:
        WARNING = "warning"

    def async_create_issue(hass, domain, issue_id, **kwargs):
        issues.append({"domain": domain, "issue_id": issue_id, **kwargs})

    core.HomeAssistant = object
    config_entries.ConfigEntry = object
    issue_registry.IssueSeverity = IssueSeverity
    issue_registry.async_create_issue = async_create_issue
    helpers.issue_registry = issue_registry
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry

    package = types.ModuleType("custom_components.spotify_dj")
    package.__path__ = [str(ROOT / "custom_components" / "spotify_dj")]
    sys.modules.setdefault("custom_components.spotify_dj", package)
    return issues


class RepairsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.issues = install_repairs_stubs()
        cls.repairs = importlib.import_module("custom_components.spotify_dj.repairs")

    def setUp(self) -> None:
        self.issues.clear()

    def test_missing_playlist_scope_creates_reauth_issue(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "device_token": "device-token",
                "spotify_client_id": "client-id",
                "spotify_scopes": "user-read-playback-state user-modify-playback-state",
            },
        )

        asyncio.run(self.repairs.async_create_fixable_issues(object(), entry))

        self.assertEqual(len(self.issues), 1)
        self.assertEqual(
            self.issues[0]["translation_key"],
            "missing_spotify_oauth_scopes",
        )


if __name__ == "__main__":
    unittest.main()
