from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
import unittest
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]


def install_oauth_stubs() -> None:
    if "aiohttp" not in sys.modules:
        aiohttp = types.ModuleType("aiohttp")

        class ClientTimeout:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        aiohttp.ClientTimeout = ClientTimeout
        sys.modules["aiohttp"] = aiohttp

    if "homeassistant.core" not in sys.modules:
        homeassistant = types.ModuleType("homeassistant")
        core = types.ModuleType("homeassistant.core")
        helpers = types.ModuleType("homeassistant.helpers")
        aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

        core.HomeAssistant = object
        aiohttp_client.async_get_clientsession = lambda hass: None

        sys.modules["homeassistant"] = homeassistant
        sys.modules["homeassistant.core"] = core
        sys.modules["homeassistant.helpers"] = helpers
        sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    package = types.ModuleType("custom_components.spotify_dj")
    package.__path__ = [str(ROOT / "custom_components" / "spotify_dj")]
    sys.modules["custom_components.spotify_dj"] = package


class SpotifyOAuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_oauth_stubs()
        cls.oauth = importlib.import_module("custom_components.spotify_dj.spotify_oauth")

    def test_redirect_uri_uses_spotifydj_callback_path(self) -> None:
        self.assertEqual(
            self.oauth.build_redirect_uri("https://example.ui.nabu.casa/"),
            "https://example.ui.nabu.casa/api/spotify_dj/spotify/callback",
        )

    def test_authorize_url_contains_pkce_parameters(self) -> None:
        const = importlib.import_module("custom_components.spotify_dj.const")
        url = self.oauth.build_authorize_url(
            "client-id",
            "https://example.ui.nabu.casa/api/spotify_dj/spotify/callback",
            const.DEFAULT_SPOTIFY_SCOPES,
            "state-value",
            "verifier-value",
        )

        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "accounts.spotify.com")
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["state"], ["state-value"])
        self.assertIn("playlist-read-private", query["scope"][0].split())
        self.assertIn("code_challenge", query)

    def test_ensure_spotify_scopes_adds_playlist_read_private(self) -> None:
        scopes = self.oauth.ensure_spotify_scopes(
            "user-read-playback-state user-modify-playback-state"
        )

        self.assertIn("playlist-read-private", scopes.split())
        self.assertEqual(
            self.oauth.missing_spotify_scopes(scopes),
            [],
        )

    def test_missing_spotify_scopes_reports_old_tokens(self) -> None:
        missing = self.oauth.missing_spotify_scopes(
            "user-read-playback-state user-modify-playback-state"
        )

        self.assertIn("playlist-read-private", missing)


if __name__ == "__main__":
    unittest.main()
