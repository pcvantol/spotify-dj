from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest


def install_media_player_stubs() -> None:
    ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    components = sys.modules.setdefault(
        "homeassistant.components",
        types.ModuleType("homeassistant.components"),
    )
    media_player = types.ModuleType("homeassistant.components.media_player")
    media_player_const = types.ModuleType("homeassistant.components.media_player.const")
    config_entries = types.ModuleType("homeassistant.config_entries")
    const = types.ModuleType("homeassistant.const")
    core = types.ModuleType("homeassistant.core")
    helpers = sys.modules.setdefault("homeassistant.helpers", types.ModuleType("homeassistant.helpers"))
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

    class MediaPlayerEntity:
        def async_write_ha_state(self):
            self.wrote_state = True

    class Feature:
        PLAY = 1
        PAUSE = 2
        NEXT_TRACK = 4
        PREVIOUS_TRACK = 8
        VOLUME_SET = 16
        SELECT_SOURCE = 32
        PLAY_MEDIA = 64

    class State:
        PLAYING = "playing"
        PAUSED = "paused"
        IDLE = "idle"
        UNAVAILABLE = "unavailable"

    media_player.MediaPlayerEntity = MediaPlayerEntity
    media_player.MediaPlayerEntityFeature = Feature
    media_player_const.MediaPlayerState = State
    config_entries.ConfigEntry = object
    const.PERCENTAGE = "%"
    core.HomeAssistant = object
    core.callback = lambda func: func
    device_registry.DeviceInfo = dict
    entity_platform.AddEntitiesCallback = object
    components.media_player = media_player
    helpers.device_registry = device_registry
    helpers.entity_platform = entity_platform
    ha.components = components

    sys.modules["homeassistant.components.media_player"] = media_player
    sys.modules["homeassistant.components.media_player.const"] = media_player_const
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.const"] = const
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform


class DJConnectMediaPlayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_media_player_stubs()
        cls.media_player = importlib.import_module("custom_components.djconnect.media_player")

    def test_media_player_represents_backend_playback(self) -> None:
        runtime = types.SimpleNamespace(
            entry=types.SimpleNamespace(entry_id="entry-1"),
            device_token="device-token",
            device_status={
                "device_id": "djconnect-lilygo-90B70990A994",
                "firmware": "3.0.4",
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
        self.assertEqual(entity.volume_level, 0.5)
        self.assertEqual(entity.source, "Living room")
        self.assertEqual(entity.source_list, ["Living room"])
        self.assertEqual(entity.extra_state_attributes["represents"], "backend_playback_session")

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
            asyncio.run(entity.async_select_source("Living room"))
            asyncio.run(entity.async_set_volume_level(0.5))
            asyncio.run(entity.async_set_shuffle(True))
            asyncio.run(entity.async_set_repeat("context"))
            asyncio.run(entity.async_play_media("playlist", "spotify:playlist:abc"))
        finally:
            self.media_player.handle_spotify_command = original

        self.assertIn(("play", None, None), calls)
        self.assertIn(("pause", None, None), calls)
        self.assertIn(("set_output", "dev-1", False), calls)
        self.assertIn(("set_volume", 30, None), calls)
        self.assertIn(("set_shuffle", True, None), calls)
        self.assertIn(("set_repeat", "context", None), calls)
        self.assertIn(("start_playlist", "spotify:playlist:abc", None), calls)

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
