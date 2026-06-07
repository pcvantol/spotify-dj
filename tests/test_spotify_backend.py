from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install_backend_stubs() -> list[dict]:
    issues: list[dict] = []
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    core = sys.modules.setdefault("homeassistant.core", types.ModuleType("homeassistant.core"))
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    aiohttp_client = sys.modules.setdefault("homeassistant.helpers.aiohttp_client", types.ModuleType("homeassistant.helpers.aiohttp_client"))
    issue_registry = types.ModuleType("homeassistant.helpers.issue_registry")

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class IssueSeverity:
        WARNING = "warning"

    def async_create_issue(hass, domain, issue_id, **kwargs):
        issues.append({"domain": domain, "issue_id": issue_id, **kwargs})

    aiohttp.ClientTimeout = ClientTimeout
    core.HomeAssistant = object
    aiohttp_client.async_get_clientsession = lambda hass: types.SimpleNamespace()
    issue_registry.IssueSeverity = IssueSeverity
    issue_registry.async_create_issue = async_create_issue
    helpers.issue_registry = issue_registry
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry

    package = types.ModuleType("custom_components.spotify_dj")
    package.__path__ = [str(ROOT / "custom_components" / "spotify_dj")]
    sys.modules.setdefault("custom_components.spotify_dj", package)
    return issues


class SpotifyBackendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.issues = install_backend_stubs()
        cls.backend = importlib.import_module("custom_components.spotify_dj.spotify_backend")
        cls.oauth = importlib.import_module("custom_components.spotify_dj.spotify_oauth")

    def setUp(self) -> None:
        self.issues.clear()

    def test_invalid_grant_creates_reauth_issue_and_friendly_error(self) -> None:
        async def revoked(*args, **kwargs):
            raise self.oauth.SpotifyTokenRefreshError(
                400,
                {"error": "invalid_grant", "error_description": "Refresh token revoked"},
            )

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "secret-refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(entry=entry, latest_spotify_refresh_token=None)
        runtime.config = dict(entry.data)
        runtime.update = lambda **kwargs: setattr(runtime, "last_update", kwargs)
        backend = self.backend.SpotifyBackend(object(), runtime)

        original = self.backend.refresh_access_token
        self.backend.refresh_access_token = revoked
        try:
            with self.assertRaises(self.backend.SpotifyReauthRequiredError) as captured:
                asyncio.run(backend._access_token())
        finally:
            self.backend.refresh_access_token = original

        self.assertIn("Reauthorize SpotifyDJ", str(captured.exception))
        self.assertEqual(runtime.last_update["last_error"], str(captured.exception))
        self.assertEqual(self.issues[0]["translation_key"], "spotify_refresh_token_revoked")
        self.assertNotIn("secret-refresh", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
