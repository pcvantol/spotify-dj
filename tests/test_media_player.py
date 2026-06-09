from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def install_media_player_stubs() -> None:
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = sys.modules.setdefault(
        "homeassistant.components",
        types.ModuleType("homeassistant.components"),
    )
    http_component = types.ModuleType("homeassistant.components.http")
    button = types.ModuleType("homeassistant.components.button")
    media_player = types.ModuleType("homeassistant.components.media_player")
    media_player_const = types.ModuleType("homeassistant.components.media_player.const")
    config_entries = types.ModuleType("homeassistant.config_entries")
    const = types.ModuleType("homeassistant.const")
    core = types.ModuleType("homeassistant.core")
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    helpers_typing = types.ModuleType("homeassistant.helpers.typing")

    class MediaPlayerEntity:
        def async_write_ha_state(self):
            self.wrote_state = True

    class ButtonEntity:
        def async_write_ha_state(self):
            self.wrote_state = True

    class HomeAssistantView:
        def json(self, payload, status_code=200):
            return {"status_code": status_code, "payload": payload}

    class Feature:
        PLAY = 1
        PAUSE = 2
        PLAY_PAUSE = 4
        NEXT_TRACK = 8
        PREVIOUS_TRACK = 16
        VOLUME_SET = 32
        SELECT_SOURCE = 64
        PLAY_MEDIA = 128

    class State:
        PLAYING = "playing"
        PAUSED = "paused"
        IDLE = "idle"
        UNAVAILABLE = "unavailable"

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.web = types.SimpleNamespace(Response=object)
    http_component.HomeAssistantView = HomeAssistantView
    button.ButtonEntity = ButtonEntity
    media_player.MediaPlayerEntity = MediaPlayerEntity
    media_player.MediaPlayerEntityFeature = Feature
    media_player_const.MediaPlayerState = State
    config_entries.ConfigEntry = object
    const.PERCENTAGE = "%"
    core.HomeAssistant = object
    core.ServiceCall = object
    core.callback = lambda func: func
    aiohttp_client.async_get_clientsession = lambda hass: None
    device_registry.DeviceInfo = dict
    entity_platform.AddEntitiesCallback = object
    helpers_typing.ConfigType = dict
    components.media_player = media_player
    components.button = button
    components.http = http_component
    helpers.aiohttp_client = aiohttp_client
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    helpers.typing = helpers_typing
    ha.components = components

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    package.DEFAULT_TEST_TTS_TEXT = "Test de DJConnect response flow"

    async def async_speak_dj_test(hass, runtime, text):
        return {"success": True, "text": text}

    package.async_speak_dj_test = async_speak_dj_test
    sys.modules["custom_components.djconnect"] = package

    sys.modules["homeassistant.components.http"] = http_component
    sys.modules["homeassistant.components.button"] = button
    sys.modules["homeassistant.components.media_player"] = media_player
    sys.modules["homeassistant.components.media_player.const"] = media_player_const
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.const"] = const
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    sys.modules["homeassistant.helpers.typing"] = helpers_typing


class DJConnectMediaPlayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_media_player_stubs()
        cls.media_player = importlib.import_module("custom_components.djconnect.media_player")
        cls.button = importlib.import_module("custom_components.djconnect.button")

    def test_media_player_represents_backend_playback(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_token="device-token",
            device_status={
                "device_id": "djconnect-lilygo-90B70990A994",
                "firmware": "3.0.6",
                "available_outputs": [{"id": "dev-1", "name": "Living room"}],
            },
            last_error=None,
            last_playback={
                "has_playback": True,
                "is_playing": True,
                "track_name": "Alive",
                "artist_name": "Pearl Jam",
                "album_name": "Ten",
                "album_image_url": "https://example.test/cover.jpg",
                "volume_percent": 30,
                "device": {"id": "dev-1", "name": "Living room"},
            },
            listeners=[],
        )
        entity = self.media_player.DJConnectPlaybackProxyMediaPlayer(runtime, object())

        self.assertEqual(entity.state, "playing")
        self.assertEqual(entity.media_title, "Alive")
        self.assertEqual(entity.media_artist, "Pearl Jam")
        self.assertEqual(entity.media_album_name, "Ten")
        self.assertEqual(entity.entity_picture, "https://example.test/cover.jpg")
        self.assertEqual(entity.media_image_url, "https://example.test/cover.jpg")
        self.assertEqual(entity.volume_level, 0.5)
        self.assertEqual(entity.source, "Living room")
        self.assertEqual(entity.source_list, ["Living room"])
        self.assertEqual(entity.extra_state_attributes["represents"], "backend_playback_session")

    def test_media_player_entity_picture_uses_image_aliases(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_token="device-token",
            device_status={},
            last_error=None,
            last_playback={
                "has_playback": True,
                "is_playing": True,
                "media_image_url": "https://example.test/media.jpg",
            },
            listeners=[],
        )
        entity = self.media_player.DJConnectPlaybackProxyMediaPlayer(runtime, object())

        self.assertEqual(entity.entity_picture, "https://example.test/media.jpg")

        runtime.last_playback = {
            "has_playback": True,
            "is_playing": True,
            "image_url": "https://example.test/image.jpg",
        }
        self.assertEqual(entity.entity_picture, "https://example.test/image.jpg")

    def test_media_player_commands_use_backend_handler(self) -> None:
        calls = []
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_token="device-token",
            device_status={"available_outputs": [{"id": "dev-1", "name": "Living room"}]},
            last_error=None,
            last_playback={"has_playback": True, "is_playing": False},
            listeners=[],
            update=lambda **kwargs: calls.append(("update", kwargs)),
        )
        entity = self.media_player.DJConnectPlaybackProxyMediaPlayer(runtime, object())

        async def fake_handler(hass, runtime_arg, command, value=None, *, play=None):
            calls.append((command, value, play))
            return {"success": True}

        original = self.media_player.handle_spotify_command
        self.media_player.handle_spotify_command = fake_handler
        try:
            asyncio.run(entity.async_media_play())
            asyncio.run(entity.async_media_pause())
            runtime.last_playback = {"has_playback": True, "is_playing": True}
            asyncio.run(entity.async_media_play_pause())
            runtime.last_playback = {"has_playback": True, "is_playing": False}
            asyncio.run(entity.async_media_play_pause())
            asyncio.run(entity.async_select_source("Living room"))
            asyncio.run(entity.async_set_volume_level(0.5))
            asyncio.run(entity.async_set_shuffle(True))
            asyncio.run(entity.async_set_repeat("context"))
            asyncio.run(entity.async_play_media("playlist", "spotify:playlist:abc"))
        finally:
            self.media_player.handle_spotify_command = original

        self.assertIn(("play", None, None), calls)
        self.assertIn(("pause", None, None), calls)
        self.assertGreaterEqual(calls.count(("play", None, None)), 2)
        self.assertGreaterEqual(calls.count(("pause", None, None)), 2)
        self.assertIn(("set_output", "dev-1", False), calls)
        self.assertIn(("set_volume", 30, None), calls)
        self.assertIn(("set_shuffle", True, None), calls)
        self.assertIn(("set_repeat", "context", None), calls)
        self.assertIn(("start_playlist", "spotify:playlist:abc", None), calls)

    def test_next_previous_media_player_commands_go_through_device(self) -> None:
        commands = []

        async def async_device_command(hass, command, **kwargs):
            commands.append((command, kwargs))
            return {"success": True}

        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_token="device-token",
            device_status={},
            last_error=None,
            last_playback={"has_playback": True, "is_playing": True},
            listeners=[],
            update=lambda **kwargs: None,
            async_device_command=async_device_command,
        )
        entity = self.media_player.DJConnectPlaybackProxyMediaPlayer(runtime, object())

        asyncio.run(entity.async_media_next_track())
        asyncio.run(entity.async_media_previous_track())

        self.assertEqual(commands, [("next", {}), ("previous", {})])

    def test_next_previous_buttons_go_through_device(self) -> None:
        commands = []

        async def async_device_command(hass, command, **kwargs):
            commands.append((command, kwargs))
            return {"success": True}

        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_status={},
            last_playback={},
            async_device_command=async_device_command,
        )

        asyncio.run(self.button.DJConnectCommandButton(runtime, object(), "next", "next_track").async_press())
        asyncio.run(self.button.DJConnectCommandButton(runtime, object(), "previous", "previous_track").async_press())

        self.assertEqual(commands, [("next", {}), ("previous", {})])

    def test_media_player_update_handles_backend_auth_failure(self) -> None:
        updates = []

        def update_runtime(**kwargs):
            updates.append(kwargs)
            for key, value in kwargs.items():
                setattr(runtime, key, value)

        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_token="device-token",
            device_status={},
            last_error=None,
            last_playback={},
            listeners=[],
            update=update_runtime,
        )
        entity = self.media_player.DJConnectPlaybackProxyMediaPlayer(runtime, object())

        async def failing_handler(hass, runtime_arg, command, value=None, *, play=None):
            raise self.media_player.SpotifyBackendError(
                "Spotify authorization has expired or was revoked. Reauthorize DJConnect."
            )

        original = self.media_player.handle_spotify_command
        self.media_player.handle_spotify_command = failing_handler
        try:
            asyncio.run(entity.async_update())
        finally:
            self.media_player.handle_spotify_command = original

        self.assertFalse(runtime.device_status["backend_available"])
        self.assertEqual(entity.state, "unavailable")


if __name__ == "__main__":
    unittest.main()
