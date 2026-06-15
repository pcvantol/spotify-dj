from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
import time
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

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules.setdefault("custom_components.djconnect", package)
    return issues


class SpotifyBackendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.issues = install_backend_stubs()
        cls.backend = importlib.import_module("custom_components.djconnect.spotify_backend")
        cls.oauth = importlib.import_module("custom_components.djconnect.spotify_oauth")

    def setUp(self) -> None:
        self.issues.clear()

    def test_spotify_search_type_supports_track_album_and_playlist(self) -> None:
        self.assertEqual(self.backend._spotify_search_type("track"), "track")
        self.assertEqual(self.backend._spotify_search_type("album"), "album")
        self.assertEqual(self.backend._spotify_search_type("playlist"), "playlist")
        self.assertEqual(self.backend._spotify_search_type("artist"), "artist")

    def test_normalize_playback_exposes_best_album_art_for_media_player(self) -> None:
        playback = self.backend._normalize_playback(
            {
                "is_playing": True,
                "context": {"uri": "spotify:playlist:abc"},
                "item": {
                    "name": "Song",
                    "uri": "spotify:track:123",
                    "artists": [{"name": "Artist"}],
                    "album": {
                        "name": "Album",
                        "images": [
                            {"url": "https://example.test/small.jpg", "width": 64, "height": 64},
                            {"url": "https://example.test/large.jpg", "width": 640, "height": 640},
                        ],
                    },
                },
                "device": {"name": "iPhone", "volume_percent": 30},
            }
        )

        self.assertEqual(playback["album_image_url"], "https://example.test/large.jpg")
        self.assertEqual(playback["media_image_url"], "https://example.test/large.jpg")
        self.assertEqual(playback["uri"], "spotify:track:123")
        self.assertEqual(playback["current_uri"], "spotify:track:123")
        self.assertEqual(playback["context_uri"], "spotify:playlist:abc")
        self.assertEqual(playback["queue_context"], "spotify:playlist:abc")
        self.assertEqual(
            playback["context"],
            {"type": "", "uri": "spotify:playlist:abc", "href": ""},
        )

    def test_empty_playback_does_not_clear_cached_sensor_fields(self) -> None:
        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return {}

            async def text(self):
                return "{}"

        class Session:
            def request(self, method, url, **kwargs):
                return Response()

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="access",
            spotify_access_token_expires_at=time.time() + 1800,
            device_status={
                "volume": 35,
                "last_track": "Alive",
                "sound_output": "Living room",
                "ha_pairing_status": "paired",
            },
            update=lambda **kwargs: setattr(runtime, "last_update", kwargs),
        )
        runtime.config = dict(entry.data)
        backend = self.backend.SpotifyBackend(object(), runtime)
        backend.session = Session()

        playback = asyncio.run(backend.playback_state())

        self.assertFalse(playback["has_playback"])
        self.assertEqual(runtime.device_status["spotify_status"], "idle")
        self.assertEqual(runtime.device_status["volume"], 35)
        self.assertEqual(runtime.device_status["last_track"], "Alive")
        self.assertEqual(runtime.device_status["sound_output"], "Living room")
        self.assertEqual(runtime.device_status["ha_pairing_status"], "paired")

    def test_play_search_query_resolves_to_spotify_uri_before_playback(self) -> None:
        class Response:
            def __init__(self, status, payload=None):
                self.status = status
                self.payload = payload or {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return self.payload

            async def text(self):
                return str(self.payload)

        class Session:
            def __init__(self):
                self.calls = []

            def request(self, method, url, **kwargs):
                self.calls.append({"method": method, "url": url, **kwargs})
                if method == "GET" and "/search?" in url:
                    return Response(
                        200,
                        {
                            "artists": {
                                "total": 1,
                                "items": [
                                    {
                                        "name": "Pearl Jam",
                                        "uri": "spotify:artist:pearl-jam",
                                    }
                                ],
                            }
                        },
                    )
                return Response(204)

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "spotify_client_id": "client-id",
                "spotify_refresh_token": "refresh",
                "spotify_market": "NL",
            },
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="access",
            spotify_access_token_expires_at=time.time() + 1800,
            device_status={},
            update=lambda **kwargs: setattr(runtime, "last_update", kwargs),
        )
        runtime.config = dict(entry.data)
        backend = self.backend.SpotifyBackend(object(), runtime)
        session = Session()
        backend.session = session

        asyncio.run(backend.play({"query": "ik wil pearl jam starten", "type": "music"}))

        self.assertIn("/search?", session.calls[0]["url"])
        self.assertIn("q=ik+wil+pearl+jam+starten", session.calls[0]["url"])
        self.assertIn("type=artist", session.calls[0]["url"])
        self.assertEqual(session.calls[0]["method"], "GET")
        self.assertEqual(session.calls[1]["method"], "PUT")
        self.assertEqual(
            session.calls[1]["json"],
            {"context_uri": "spotify:artist:pearl-jam"},
        )
        self.assertEqual(runtime.last_resolved_media["title"], "")
        self.assertEqual(runtime.last_resolved_media["artist"], "Pearl Jam")
        self.assertEqual(runtime.last_resolved_media["uri"], "spotify:artist:pearl-jam")
        self.assertEqual(runtime.last_spotify_search["query"], "ik wil pearl jam starten")
        self.assertEqual(runtime.last_spotify_search["type"], "artist")
        self.assertEqual(runtime.last_spotify_search["returned"], 1)
        self.assertEqual(
            runtime.last_spotify_search["selected"]["uri"],
            "spotify:artist:pearl-jam",
        )

    def test_play_recovers_no_active_device_by_transferring_to_configured_source(self) -> None:
        class Response:
            def __init__(self, status, payload=None):
                self.status = status
                self.payload = payload or {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return self.payload

            async def text(self):
                return str(self.payload)

        class Session:
            def __init__(self):
                self.calls = []
                self.play_attempts = 0

            def request(self, method, url, **kwargs):
                self.calls.append({"method": method, "url": url, **kwargs})
                if method == "PUT" and url.endswith("/me/player/play"):
                    self.play_attempts += 1
                    if self.play_attempts == 1:
                        return Response(
                            404,
                            {"error": {"message": "No active device found"}},
                        )
                    return Response(204)
                if method == "GET" and url.endswith("/me/player/devices"):
                    return Response(
                        200,
                        {
                            "devices": [
                                {"id": "dev-1", "name": "Kitchen", "is_active": False},
                                {"id": "dev-2", "name": "Living room", "is_active": False},
                            ]
                        },
                    )
                return Response(204)

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "spotify_client_id": "client-id",
                "spotify_refresh_token": "refresh",
                "spotify_source": "Living room",
            },
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="access",
            spotify_access_token_expires_at=time.time() + 1800,
            backend_cache={},
            device_status={},
            update=lambda **kwargs: setattr(runtime, "last_update", kwargs),
        )
        runtime.config = dict(entry.data)
        backend = self.backend.SpotifyBackend(object(), runtime)
        session = Session()
        backend.session = session

        asyncio.run(backend.play("spotify:track:alive"))

        self.assertEqual(session.play_attempts, 2)
        transfer = next(call for call in session.calls if call["url"].endswith("/me/player"))
        self.assertEqual(transfer["json"], {"device_ids": ["dev-2"], "play": False})

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

        self.assertIn("Reauthorize DJConnect", str(captured.exception))
        self.assertEqual(runtime.last_update["last_error"], str(captured.exception))
        self.assertEqual(self.issues[0]["translation_key"], "spotify_refresh_token_revoked")
        self.assertNotIn("secret-refresh", str(captured.exception))

    def test_concurrent_access_token_refresh_uses_single_refresh_call(self) -> None:
        calls = []

        async def refresh(*args, **kwargs):
            calls.append(kwargs["refresh_token"])
            await asyncio.sleep(0)
            return {"access_token": "new-access", "expires_in": 3600}

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token=None,
            spotify_access_token_expires_at=0,
        )
        runtime.config = dict(entry.data)
        backend = self.backend.SpotifyBackend(object(), runtime)

        original = self.backend.refresh_access_token
        self.backend.refresh_access_token = refresh
        try:
            async def run_concurrent():
                return await asyncio.gather(
                    backend._access_token(),
                    backend._access_token(),
                )

            tokens = asyncio.run(run_concurrent())
        finally:
            self.backend.refresh_access_token = original

        self.assertEqual(tokens, ["new-access", "new-access"])
        self.assertEqual(calls, ["refresh"])

    def test_invalid_grant_retries_when_refresh_token_rotated_during_refresh(self) -> None:
        calls = []

        async def refresh(*args, **kwargs):
            refresh_token = kwargs["refresh_token"]
            calls.append(refresh_token)
            if refresh_token == "old-refresh":
                runtime.latest_spotify_refresh_token = "new-refresh"
                raise self.oauth.SpotifyTokenRefreshError(
                    400,
                    {"error": "invalid_grant", "error_description": "Refresh token revoked"},
                )
            return {"access_token": "new-access", "expires_in": 3600}

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "old-refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token=None,
            spotify_access_token_expires_at=0,
        )
        runtime.config = dict(entry.data)
        runtime.update = lambda **kwargs: setattr(runtime, "last_update", kwargs)
        backend = self.backend.SpotifyBackend(object(), runtime)

        original = self.backend.refresh_access_token
        self.backend.refresh_access_token = refresh
        try:
            token = asyncio.run(backend._access_token())
        finally:
            self.backend.refresh_access_token = original

        self.assertEqual(token, "new-access")
        self.assertEqual(calls, ["old-refresh", "new-refresh"])
        self.assertEqual(self.issues, [])
        self.assertFalse(hasattr(runtime, "last_update"))

    def test_invalid_grant_retries_entry_token_when_runtime_token_is_stale(self) -> None:
        calls = []

        async def refresh(*args, **kwargs):
            refresh_token = kwargs["refresh_token"]
            calls.append(refresh_token)
            if refresh_token == "old-runtime-refresh":
                raise self.oauth.SpotifyTokenRefreshError(
                    400,
                    {"error": "invalid_grant", "error_description": "Refresh token revoked"},
                )
            return {"access_token": "new-access", "expires_in": 3600}

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "spotify_client_id": "client-id",
                "spotify_refresh_token": "new-entry-refresh",
            },
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token="old-runtime-refresh",
            spotify_access_token=None,
            spotify_access_token_expires_at=0,
        )
        runtime.config = dict(entry.data)
        runtime.update = lambda **kwargs: setattr(runtime, "last_update", kwargs)
        backend = self.backend.SpotifyBackend(object(), runtime)

        original = self.backend.refresh_access_token
        self.backend.refresh_access_token = refresh
        try:
            with self.assertLogs(self.backend._LOGGER, level="DEBUG") as captured:
                token = asyncio.run(backend._access_token())
        finally:
            self.backend.refresh_access_token = original

        logs = "\n".join(captured.output)
        self.assertEqual(token, "new-access")
        self.assertEqual(calls, ["old-runtime-refresh", "new-entry-refresh"])
        self.assertEqual(self.issues, [])
        self.assertIn("source=entry", logs)
        self.assertNotIn("old-runtime-refresh", logs)
        self.assertNotIn("new-entry-refresh", logs)

    def test_access_token_cache_avoids_unnecessary_refresh(self) -> None:
        calls = []

        async def refresh(*args, **kwargs):
            calls.append(kwargs)
            return {"access_token": "new-access", "expires_in": 3600}

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="cached-access",
            spotify_access_token_expires_at=time.time() + 1800,
        )
        runtime.config = dict(entry.data)
        runtime.update = lambda **kwargs: setattr(runtime, "last_update", kwargs)
        backend = self.backend.SpotifyBackend(object(), runtime)

        original = self.backend.refresh_access_token
        self.backend.refresh_access_token = refresh
        try:
            token = asyncio.run(backend._access_token())
        finally:
            self.backend.refresh_access_token = original

        self.assertEqual(token, "cached-access")
        self.assertEqual(calls, [])

    def test_spotify_api_401_refreshes_access_token_once_without_repair(self) -> None:
        refreshes = []

        async def refresh(*args, **kwargs):
            refreshes.append(kwargs)
            return {"access_token": f"access-{len(refreshes)}", "expires_in": 3600}

        class Response:
            def __init__(self, status, payload):
                self.status = status
                self.payload = payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return self.payload

            async def text(self):
                return str(self.payload)

        class Session:
            def __init__(self):
                self.calls = []

            def request(self, method, url, **kwargs):
                self.calls.append({"method": method, "url": url, **kwargs})
                if len(self.calls) == 1:
                    return Response(401, {"error": {"message": "The access token expired"}})
                return Response(
                    200,
                    {
                        "is_playing": True,
                        "item": {"name": "Song", "artists": [], "album": {}},
                        "device": {"name": "iPhone", "volume_percent": 30},
                    },
                )

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="expired-access",
            spotify_access_token_expires_at=time.time() + 1800,
            device_status={},
        )
        runtime.config = dict(entry.data)
        runtime.update = lambda **kwargs: setattr(runtime, "last_update", kwargs)
        backend = self.backend.SpotifyBackend(object(), runtime)
        session = Session()
        backend.session = session

        original = self.backend.refresh_access_token
        self.backend.refresh_access_token = refresh
        try:
            playback = asyncio.run(backend.playback_state())
        finally:
            self.backend.refresh_access_token = original

        self.assertTrue(playback["has_playback"])
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(len(refreshes), 1)
        self.assertEqual(session.calls[0]["headers"]["Authorization"], "Bearer expired-access")
        self.assertEqual(session.calls[1]["headers"]["Authorization"], "Bearer access-1")
        self.assertEqual(self.issues, [])

    def test_shuffle_and_repeat_commands_map_to_spotify_endpoints(self) -> None:
        class Response:
            def __init__(self, status, payload=None):
                self.status = status
                self.payload = payload or {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return self.payload

            async def text(self):
                return str(self.payload)

        class Session:
            def __init__(self):
                self.calls = []

            def request(self, method, url, **kwargs):
                self.calls.append({"method": method, "url": url, **kwargs})
                if method == "GET":
                    return Response(
                        200,
                        {
                            "is_playing": True,
                            "shuffle_state": True,
                            "repeat_state": "context",
                            "item": {"name": "Song", "artists": [], "album": {}},
                            "device": {"name": "iPhone", "volume_percent": 30},
                        },
                    )
                return Response(204)

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        updates = []
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="access",
            spotify_access_token_expires_at=time.time() + 1800,
            device_status={},
            update=lambda **kwargs: updates.append(kwargs),
        )
        runtime.config = dict(entry.data)
        session = Session()

        original_clientsession = self.backend.async_get_clientsession
        self.backend.async_get_clientsession = lambda hass: session
        try:
            shuffle = asyncio.run(
                self.backend.handle_spotify_command(
                    object(),
                    runtime,
                    "set_shuffle",
                    True,
                )
            )
            repeat = asyncio.run(
                self.backend.handle_spotify_command(
                    object(),
                    runtime,
                    "set_repeat",
                    "context",
                )
            )
        finally:
            self.backend.async_get_clientsession = original_clientsession

        urls = [call["url"] for call in session.calls]
        self.assertIn(
            "https://api.spotify.com/v1/me/player/shuffle?state=true",
            urls,
        )
        self.assertIn(
            "https://api.spotify.com/v1/me/player/repeat?state=context",
            urls,
        )
        self.assertTrue(shuffle["playback"]["shuffle"])
        self.assertEqual(repeat["playback"]["repeat_state"], "context")
        self.assertEqual(runtime.device_status["shuffle"], True)
        self.assertEqual(runtime.device_status["repeat_state"], "context")

    def test_queue_command_returns_context_and_album_art(self) -> None:
        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return {
                    "queue": [
                        {
                            "name": "Next Song",
                            "uri": "spotify:track:next",
                            "artists": [{"name": "Artist"}],
                            "album": {
                                "images": [
                                    {
                                        "url": "https://example.test/queue.jpg",
                                        "width": 300,
                                        "height": 300,
                                    }
                                ]
                            },
                        }
                    ]
                }

            async def text(self):
                return "{}"

        class Session:
            def request(self, method, url, **kwargs):
                return Response()

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="access",
            spotify_access_token_expires_at=time.time() + 1800,
            device_status={},
            last_playback={"context_uri": "spotify:playlist:abc"},
            update=lambda **kwargs: None,
        )
        runtime.config = dict(entry.data)

        original_clientsession = self.backend.async_get_clientsession
        self.backend.async_get_clientsession = lambda hass: Session()
        try:
            result = asyncio.run(
                self.backend.handle_spotify_command(object(), runtime, "queue")
            )
        finally:
            self.backend.async_get_clientsession = original_clientsession

        self.assertTrue(result["success"])
        self.assertEqual(result["context_uri"], "spotify:playlist:abc")
        self.assertEqual(result["contextUri"], "spotify:playlist:abc")
        self.assertEqual(result["queue"][0]["album_image_url"], "https://example.test/queue.jpg")
        self.assertEqual(result["queue"][0]["imageUrl"], "https://example.test/queue.jpg")
        self.assertEqual(runtime.device_status["queue"]["items"], result["queue"])

    def test_queue_command_caps_client_items_at_100(self) -> None:
        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return {
                    "queue": [
                        {
                            "name": f"Song {index}",
                            "uri": f"spotify:track:{index}",
                            "artists": [{"name": "Artist"}],
                            "album": {},
                        }
                        for index in range(105)
                    ]
                }

            async def text(self):
                return "{}"

        class Session:
            def request(self, method, url, **kwargs):
                return Response()

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="access",
            spotify_access_token_expires_at=time.time() + 1800,
            device_status={},
            last_playback={},
            update=lambda **kwargs: None,
        )
        runtime.config = dict(entry.data)

        original_clientsession = self.backend.async_get_clientsession
        self.backend.async_get_clientsession = lambda hass: Session()
        try:
            result = asyncio.run(
                self.backend.handle_spotify_command(object(), runtime, "queue")
            )
        finally:
            self.backend.async_get_clientsession = original_clientsession

        self.assertEqual(len(result["queue"]), 100)
        self.assertEqual(result["queue"][-1]["title"], "Song 99")
        self.assertEqual(len(runtime.device_status["queue"]["items"]), 100)

    def test_playlists_command_returns_playlist_art_aliases(self) -> None:
        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return {
                    "items": [
                        {
                            "id": "playlist-id",
                            "name": "Default playlist",
                            "uri": "spotify:playlist:default",
                            "owner": {"display_name": "Peter"},
                            "images": [
                                {
                                    "url": "https://example.test/playlist-small.jpg",
                                    "width": 64,
                                    "height": 64,
                                },
                                {
                                    "url": "https://example.test/playlist-large.jpg",
                                    "width": 640,
                                    "height": 640,
                                },
                            ],
                        }
                    ]
                }

            async def text(self):
                return "{}"

        class Session:
            def request(self, method, url, **kwargs):
                return Response()

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="access",
            spotify_access_token_expires_at=time.time() + 1800,
            backend_cache={},
            device_status={},
            update=lambda **kwargs: None,
        )
        runtime.config = dict(entry.data)

        original_clientsession = self.backend.async_get_clientsession
        self.backend.async_get_clientsession = lambda hass: Session()
        try:
            result = asyncio.run(
                self.backend.handle_spotify_command(object(), runtime, "playlists")
            )
        finally:
            self.backend.async_get_clientsession = original_clientsession

        playlist = result["playlists"][0]
        self.assertEqual(playlist["id"], "spotify:playlist:default")
        self.assertEqual(playlist["image_url"], "https://example.test/playlist-large.jpg")
        self.assertEqual(playlist["imageUrl"], "https://example.test/playlist-large.jpg")
        self.assertEqual(playlist["album_image_url"], "https://example.test/playlist-large.jpg")
        self.assertEqual(playlist["media_image_url"], "https://example.test/playlist-large.jpg")
        self.assertEqual(runtime.device_status["playlists"], result["playlists"])

    def test_play_context_at_artist_context_plays_track_without_offset(self) -> None:
        class Response:
            status = 204

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return {}

            async def text(self):
                return ""

        class Session:
            def __init__(self):
                self.calls = []

            def request(self, method, url, **kwargs):
                self.calls.append({"method": method, "url": url, **kwargs})
                return Response()

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="access",
            spotify_access_token_expires_at=time.time() + 1800,
            device_status={},
            last_playback={"context_uri": "spotify:artist:abc"},
            update=lambda **kwargs: None,
        )
        runtime.config = dict(entry.data)
        backend = self.backend.SpotifyBackend(object(), runtime)
        session = Session()
        backend.session = session

        asyncio.run(
            backend.play_context_at(
                {
                    "context_uri": "spotify:artist:abc",
                    "offset_uri": "spotify:track:def",
                }
            )
        )

        self.assertEqual(
            session.calls[0]["json"],
            {"uris": ["spotify:track:def"]},
        )

    def test_seek_relative_uses_current_progress_and_clamps_to_duration(self) -> None:
        class Response:
            def __init__(self, status, payload=None):
                self.status = status
                self.payload = payload or {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self, content_type=None):
                return self.payload

            async def text(self):
                return str(self.payload)

        class Session:
            def __init__(self):
                self.calls = []

            def request(self, method, url, **kwargs):
                self.calls.append({"method": method, "url": url, **kwargs})
                if method == "GET" and url.endswith("/me/player"):
                    return Response(
                        200,
                        {
                            "is_playing": True,
                            "progress_ms": 175000,
                            "item": {
                                "name": "Song",
                                "duration_ms": 180000,
                                "artists": [],
                                "album": {},
                            },
                            "device": {"name": "iPhone", "volume_percent": 30},
                        },
                    )
                return Response(204)

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"spotify_client_id": "client-id", "spotify_refresh_token": "refresh"},
            options={},
        )
        runtime = types.SimpleNamespace(
            entry=entry,
            latest_spotify_refresh_token=None,
            spotify_access_token="access",
            spotify_access_token_expires_at=time.time() + 1800,
            device_status={},
            update=lambda **kwargs: None,
        )
        runtime.config = dict(entry.data)
        session = Session()

        original_clientsession = self.backend.async_get_clientsession
        self.backend.async_get_clientsession = lambda hass: session
        try:
            result = asyncio.run(
                self.backend.handle_spotify_command(
                    object(),
                    runtime,
                    "seek_relative",
                    15000,
                )
            )
        finally:
            self.backend.async_get_clientsession = original_clientsession

        self.assertTrue(result["success"])
        self.assertEqual(
            session.calls[1]["url"],
            "https://api.spotify.com/v1/me/player/seek?position_ms=180000",
        )

    def test_set_play_mode_is_no_longer_supported(self) -> None:
        runtime = types.SimpleNamespace(config={})
        with self.assertRaises(ValueError):
            asyncio.run(
                self.backend.handle_spotify_command(
                    object(),
                    runtime,
                    "set_play_mode",
                    "shuffle",
                )
            )


if __name__ == "__main__":
    unittest.main()
