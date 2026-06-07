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
    deleted: list[dict] = []
    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    voluptuous = sys.modules.setdefault("voluptuous", types.ModuleType("voluptuous"))
    components = sys.modules.setdefault(
        "homeassistant.components",
        types.ModuleType("homeassistant.components"),
    )
    repairs_component = types.ModuleType("homeassistant.components.repairs")
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
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )
    issue_registry = types.ModuleType("homeassistant.helpers.issue_registry")

    class IssueSeverity:
        WARNING = "warning"

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class RepairsFlow:
        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

        def async_abort(self, **kwargs):
            return {"type": "abort", **kwargs}

    def async_create_issue(hass, domain, issue_id, **kwargs):
        issues.append({"domain": domain, "issue_id": issue_id, **kwargs})

    def async_delete_issue(hass, domain, issue_id):
        deleted.append({"domain": domain, "issue_id": issue_id})

    voluptuous.Schema = lambda schema: schema
    core.HomeAssistant = object
    config_entries.ConfigEntry = object
    aiohttp.ClientTimeout = ClientTimeout
    repairs_component.RepairsFlow = RepairsFlow
    issue_registry.IssueSeverity = IssueSeverity
    issue_registry.async_create_issue = async_create_issue
    issue_registry.async_delete_issue = async_delete_issue
    aiohttp_client.async_get_clientsession = lambda hass: None
    components.repairs = repairs_component
    helpers.issue_registry = issue_registry
    helpers.aiohttp_client = aiohttp_client
    sys.modules["homeassistant.components.repairs"] = repairs_component
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry
    install_repairs_stubs.deleted = deleted

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
                "spotify_refresh_token": "refresh-token",
                "spotify_scopes": "user-read-playback-state user-modify-playback-state",
            },
        )

        asyncio.run(self.repairs.async_create_fixable_issues(object(), entry))

        self.assertEqual(len(self.issues), 1)
        self.assertEqual(
            self.issues[0]["translation_key"],
            "missing_spotify_oauth_scopes",
        )

    def test_missing_spotify_refresh_token_creates_issue(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "device_token": "device-token",
                "spotify_client_id": "client-id",
                "spotify_scopes": (
                    "user-read-playback-state user-modify-playback-state "
                    "user-read-currently-playing user-library-read "
                    "playlist-read-private playlist-read-collaborative "
                    "user-read-recently-played user-top-read"
                ),
            },
        )

        asyncio.run(self.repairs.async_create_fixable_issues(object(), entry))

        self.assertEqual(len(self.issues), 1)
        self.assertEqual(
            self.issues[0]["translation_key"],
            "missing_spotify_refresh_token",
        )

    def test_spotify_reauth_issue_is_fixable(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "device_token": "device-token",
                "spotify_client_id": "client-id",
                "spotify_scopes": (
                    "user-read-playback-state user-modify-playback-state "
                    "user-read-currently-playing user-library-read "
                    "playlist-read-private playlist-read-collaborative "
                    "user-read-recently-played user-top-read"
                ),
            },
        )

        asyncio.run(self.repairs.async_create_fixable_issues(object(), entry))

        self.assertTrue(self.issues[0]["is_fixable"])
        self.assertEqual(self.issues[0]["data"], {"entry_id": "entry-1"})

    def test_spotify_reauth_fix_flow_creates_oauth_pending_context(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "ha_external_url": "https://example.ui.nabu.casa",
                "spotify_client_id": "client-id",
                "spotify_market": "NL",
            },
        )

        class ConfigEntries:
            def async_get_entry(self, entry_id):
                return entry if entry_id == "entry-1" else None

        hass = types.SimpleNamespace(
            data={},
            config_entries=ConfigEntries(),
            config=types.SimpleNamespace(external_url=""),
        )

        flow = asyncio.run(
            self.repairs.async_create_fix_flow(
                hass,
                "entry-1_spotify_refresh_token_revoked",
                {"entry_id": "entry-1"},
            )
        )
        result = asyncio.run(flow.async_step_init())

        self.assertEqual(result["type"], "form")
        self.assertIn("authorize_url", result["description_placeholders"])
        self.assertEqual(len(hass.data["spotify_dj"]["spotify_oauth_pending"]), 1)

    def test_spotify_reauth_fix_flow_deletes_issue_after_token_exists(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_refresh_token": "new-token"},
        )

        class ConfigEntries:
            def async_get_entry(self, entry_id):
                return entry

        hass = types.SimpleNamespace(data={}, config_entries=ConfigEntries())
        flow = self.repairs.SpotifyOAuthRepairFlow(
            hass,
            "entry-1_spotify_refresh_token_revoked",
            {"entry_id": "entry-1"},
        )

        result = asyncio.run(flow.async_step_init({}))

        self.assertEqual(result["type"], "create_entry")
        self.assertIn(
            {"domain": "spotify_dj", "issue_id": "entry-1_spotify_refresh_token_revoked"},
            install_repairs_stubs.deleted,
        )


if __name__ == "__main__":
    unittest.main()
