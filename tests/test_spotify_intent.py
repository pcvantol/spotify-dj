from __future__ import annotations

import importlib
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


if __name__ == "__main__":
    unittest.main()
