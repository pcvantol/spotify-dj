from __future__ import annotations

import importlib
import asyncio
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def install_spotify_stubs() -> None:
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    helpers = sys.modules.setdefault(
        "homeassistant.helpers",
        types.ModuleType("homeassistant.helpers"),
    )
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    aiohttp.ClientTimeout = ClientTimeout
    aiohttp_client.async_get_clientsession = lambda hass: None
    helpers.aiohttp_client = aiohttp_client
    if "homeassistant.core" not in sys.modules:
        homeassistant = types.ModuleType("homeassistant")
        core = types.ModuleType("homeassistant.core")
        core.HomeAssistant = object
        sys.modules["homeassistant"] = homeassistant
        sys.modules["homeassistant.core"] = core
    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules.setdefault("custom_components.djconnect", package)


class SpotifyIntentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_spotify_stubs()
        cls.spotify = importlib.import_module("custom_components.djconnect.spotify")

    def test_spoken_dutch_mood_request_extracts_artist(self) -> None:
        media, media_type = self.spotify._media_from_intent(
            {
                "type": "search",
                "spotify_search_query": "ik heb wel zin in Nirvana",
            },
            {},
        )

        self.assertEqual(media, "Nirvana")
        self.assertEqual(media_type, "artist")

    def test_spoken_command_variants_extract_artist(self) -> None:
        examples = {
            "ik heb zin in Pearl Jam": "Pearl Jam",
            "ik wil Metallica horen": "Metallica",
            "ik wil wel Metallica horen": "Metallica",
            "ik wil wel Metallica luisteren": "Metallica",
            "Nirvana wil ik wel horen": "Nirvana",
            "zet Radiohead op": "Radiohead",
            "zet heavn aan": "heavn",
            "zet london grammer op": "london grammer",
            "speel even The Cure": "The Cure",
            "speel maar af Above & Beyond": "Above & Beyond",
            "speel maar af above en beyond": "above en beyond",
            "I feel like Fleetwood Mac": "Fleetwood Mac",
        }

        for text, expected in examples.items():
            with self.subTest(text=text):
                media, media_type = self.spotify._media_from_intent(
                    {"type": "search", "spotify_search_query": text},
                    {},
                )
                self.assertEqual(media, expected)
                self.assertEqual(media_type, "artist")

    def test_spoken_playlist_variants_extract_playlist(self) -> None:
        examples = {
            "speel playlist Roadtrip": "Roadtrip",
            "start mijn playlist Rustig wakker worden": "Rustig wakker worden",
            "zet afspeellijst Dinner Jazz op": "Dinner Jazz",
            "draai Sunday Morning playlist": "Sunday Morning",
            "play playlist Workout": "Workout",
            "put on Chill playlist": "Chill",
        }

        for text, expected in examples.items():
            with self.subTest(text=text):
                media, media_type = self.spotify._media_from_intent(
                    {"type": "search", "spotify_search_query": text},
                    {},
                )
                self.assertEqual(media, expected)
                self.assertEqual(media_type, "playlist")

    def test_spoken_track_variants_extract_track(self) -> None:
        examples = {
            "speel nummer Black van Pearl Jam": "Black Pearl Jam",
            "start het liedje Everlong": "Everlong",
            "zet track Nothing Else Matters van Metallica op": "Nothing Else Matters Metallica",
            "draai nummer Teardrop van Massive Attack": "Teardrop Massive Attack",
            "play song Paranoid Android by Radiohead": "Paranoid Android Radiohead",
            "put on track Heroes by David Bowie": "Heroes David Bowie",
        }

        for text, expected in examples.items():
            with self.subTest(text=text):
                media, media_type = self.spotify._media_from_intent(
                    {"type": "search", "spotify_search_query": text},
                    {},
                )
                self.assertEqual(media, expected)
                self.assertEqual(media_type, "track")

    def test_spoken_album_variants_extract_album(self) -> None:
        examples = {
            "speel album Ten van Pearl Jam": "Ten Pearl Jam",
            "start het album Nevermind": "Nevermind",
            "zet de plaat OK Computer van Radiohead op": "OK Computer Radiohead",
            "draai album Rumours van Fleetwood Mac": "Rumours Fleetwood Mac",
            "play album In Rainbows by Radiohead": "In Rainbows Radiohead",
            "put on the album Blue": "Blue",
        }

        for text, expected in examples.items():
            with self.subTest(text=text):
                media, media_type = self.spotify._media_from_intent(
                    {"type": "search", "spotify_search_query": text},
                    {},
                )
                self.assertEqual(media, expected)
                self.assertEqual(media_type, "album")

    def test_spoken_default_playlist_variants_use_configured_playlist(self) -> None:
        examples = (
            "speel standaard playlist",
            "start mijn favorieten",
            "zet liked songs op",
            "play default playlist",
            "start my favorites",
        )

        for text in examples:
            with self.subTest(text=text):
                media, media_type = self.spotify._media_from_intent(
                    {"type": "search", "spotify_search_query": text},
                    {"liked_proxy_playlist_uri": "spotify:playlist:default"},
                )
                self.assertEqual(media, "spotify:playlist:default")
                self.assertEqual(media_type, "playlist")

    def test_explicit_artist_intent_wins_over_fallback_text(self) -> None:
        media, media_type = self.spotify._media_from_intent(
            {
                "type": "search",
                "artist": "Nirvana",
                "spotify_search_query": "ik heb wel zin in iets",
            },
            {},
        )

        self.assertEqual(media, "Nirvana")
        self.assertEqual(media_type, "artist")

    def test_explicit_track_and_album_intents_use_specific_search_types(self) -> None:
        media, media_type = self.spotify._media_from_intent(
            {
                "type": "track",
                "title": "Black",
                "artist": "Pearl Jam",
                "spotify_search_query": "speel Pearl Jam",
            },
            {},
        )
        self.assertEqual(media, "Black Pearl Jam")
        self.assertEqual(media_type, "track")

        media, media_type = self.spotify._media_from_intent(
            {
                "type": "album",
                "album": "Nevermind",
                "artist": "Nirvana",
                "spotify_search_query": "speel Nirvana",
            },
            {},
        )
        self.assertEqual(media, "Nevermind Nirvana")
        self.assertEqual(media_type, "album")

    def test_play_from_intent_prefers_fresh_search_selection_over_stale_playback(self) -> None:
        async def command(hass, runtime, command, value, play=True):
            runtime.last_spotify_search = {
                "query": "Metallica",
                "type": "artist",
                "selected": {
                    "type": "artist",
                    "artist": "Metallica",
                    "artist_name": "Metallica",
                    "uri": "spotify:artist:metallica",
                },
            }
            return {
                "playback": {
                    "type": "artist",
                    "artist": "Guns N' Roses",
                    "artist_name": "Guns N' Roses",
                }
            }

        original = self.spotify.handle_spotify_command
        self.spotify.handle_spotify_command = command
        runtime = types.SimpleNamespace(
            last_resolved_media={
                "type": "artist",
                "artist": "Guns N' Roses",
                "artist_name": "Guns N' Roses",
            },
            last_spotify_search=None,
        )
        try:
            result = asyncio.run(
                self.spotify.play_from_intent(
                    object(),
                    runtime,
                    {"type": "search", "spotify_search_query": "Metallica"},
                    {},
                )
            )
        finally:
            self.spotify.handle_spotify_command = original

        self.assertEqual(result["resolved_media"]["artist"], "Metallica")
        self.assertEqual(result["device_response"]["playback"]["artist"], "Guns N' Roses")

    def test_play_from_intent_does_not_reuse_stale_resolved_media_on_query_mismatch(self) -> None:
        async def command(hass, runtime, command, value, play=True):
            runtime.last_spotify_search = {
                "query": "Nirvana",
                "type": "artist",
                "selected": {},
            }
            return {
                "playback": {
                    "type": "artist",
                    "artist": "Red Hot Chili Peppers",
                    "artist_name": "Red Hot Chili Peppers",
                }
            }

        original = self.spotify.handle_spotify_command
        self.spotify.handle_spotify_command = command
        runtime = types.SimpleNamespace(
            last_resolved_media={
                "type": "artist",
                "artist": "Red Hot Chili Peppers",
                "artist_name": "Red Hot Chili Peppers",
            },
            last_spotify_search=None,
        )
        try:
            result = asyncio.run(
                self.spotify.play_from_intent(
                    object(),
                    runtime,
                    {"type": "search", "spotify_search_query": "Nirvana"},
                    {},
                )
            )
        finally:
            self.spotify.handle_spotify_command = original

        self.assertIsNone(result["resolved_media"])
        self.assertEqual(result["device_response"]["playback"]["artist"], "Red Hot Chili Peppers")


if __name__ == "__main__":
    unittest.main()
