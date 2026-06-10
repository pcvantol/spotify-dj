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

        def async_external_step(self, **kwargs):
            return {"type": "external", **kwargs}

        def async_external_step_done(self, **kwargs):
            return {"type": "external_done", **kwargs}

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

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules.setdefault("custom_components.djconnect", package)
    return issues


class RepairsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.issues = install_repairs_stubs()
        cls.repairs = importlib.import_module("custom_components.djconnect.repairs")

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

        self.assertEqual(result["type"], "external")
        self.assertEqual(result["step_id"], "init")
        self.assertEqual(result["title"], "DJConnect opnieuw autoriseren bij Spotify")
        self.assertIn("Spotify toestemming", result["description"])
        self.assertIn("https://accounts.spotify.com/authorize", result["url"])
        self.assertIn("authorize_url", result["description_placeholders"])
        self.assertIn("repair_description", result["description_placeholders"])
        self.assertEqual(len(hass.data["djconnect"]["spotify_oauth_pending"]), 1)

    def test_spotify_reauth_fix_flow_requires_new_token(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "ha_external_url": "https://example.ui.nabu.casa",
                "spotify_client_id": "client-id",
                "spotify_refresh_token": "old-token",
            },
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

        start = asyncio.run(flow.async_step_init())
        self.assertEqual(start["type"], "external")
        self.assertEqual(start["step_id"], "init")

        done = asyncio.run(flow.async_step_authorize())
        self.assertEqual(done["type"], "external_done")
        self.assertEqual(done["next_step_id"], "oauth_done")

        result = asyncio.run(flow.async_step_oauth_done({}))

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "oauth_done")
        self.assertEqual(result["errors"]["base"], "oauth_not_completed")

        entry.data["spotify_refresh_token"] = "new-token"
        result = asyncio.run(flow.async_step_oauth_done({}))

        self.assertEqual(result["type"], "create_entry")
        self.assertIn(
            {"domain": "djconnect", "issue_id": "entry-1_spotify_refresh_token_revoked"},
            install_repairs_stubs.deleted,
        )

    def test_spotify_reauth_fix_flow_accepts_token_when_missing_before(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "ha_external_url": "https://example.ui.nabu.casa",
                "spotify_client_id": "client-id",
            },
        )

        class ConfigEntries:
            def async_get_entry(self, entry_id):
                return entry

        hass = types.SimpleNamespace(
            data={},
            config_entries=ConfigEntries(),
            config=types.SimpleNamespace(external_url=""),
        )
        flow = self.repairs.SpotifyOAuthRepairFlow(
            hass,
            "entry-1_missing_spotify_refresh_token",
            {"entry_id": "entry-1"},
        )

        start = asyncio.run(flow.async_step_init())
        self.assertEqual(start["type"], "external")

        entry.data["spotify_refresh_token"] = "new-token"
        result = asyncio.run(flow.async_step_oauth_done({}))

        self.assertEqual(result["type"], "create_entry")

    def test_spotify_reauth_fix_flow_falls_back_to_single_djconnect_entry(self) -> None:
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            domain="djconnect",
            data={
                "ha_external_url": "https://example.ui.nabu.casa",
                "spotify_client_id": "client-id",
            },
        )

        class ConfigEntries:
            def async_get_entry(self, entry_id):
                return None

            def async_entries(self, domain=None):
                return [entry] if domain in (None, "djconnect") else []

        hass = types.SimpleNamespace(
            data={},
            config_entries=ConfigEntries(),
            config=types.SimpleNamespace(external_url=""),
        )
        flow = self.repairs.SpotifyOAuthRepairFlow(
            hass,
            "spotify_refresh_token_revoked",
            {},
        )

        result = asyncio.run(flow.async_step_init())

        self.assertEqual(result["type"], "external")
        self.assertEqual(result["title"], "DJConnect opnieuw autoriseren bij Spotify")
        pending = next(iter(hass.data["djconnect"]["spotify_oauth_pending"].values()))
        self.assertEqual(pending["entry_id"], "entry-1")


if __name__ == "__main__":
    unittest.main()
