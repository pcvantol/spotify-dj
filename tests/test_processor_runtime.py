from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest


from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def install_processor_stubs() -> None:
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    aiohttp.ClientTimeout = ClientTimeout
    helpers = sys.modules.setdefault(
        "homeassistant.helpers",
        types.ModuleType("homeassistant.helpers"),
    )
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )
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


class Runtime:
    config = {}

    def __init__(self) -> None:
        self.updates = []

    def update(self, **kwargs):
        self.updates.append(kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)


class ProcessorRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_processor_stubs()
        cls.processor = importlib.import_module("custom_components.djconnect.processor")

    def test_process_text_command_updates_text_before_processing_result(self) -> None:
        async def assist(hass, user_text, conf):
            return {
                "type": "search",
                "spotify_search_query": user_text,
                "dj_announcement": "Daar gaan we.",
            }

        async def play(hass, runtime, intent, conf):
            return {
                "resolved_media": {
                    "title": "Black",
                    "artist": "Pearl Jam",
                    "album_name": "Ten",
                }
            }

        original_assist = self.processor.process_text_with_assist
        original_play = self.processor.play_from_intent
        self.processor.process_text_with_assist = assist
        self.processor.play_from_intent = play
        runtime = Runtime()
        try:
            result = asyncio.run(
                self.processor.process_text_command(
                    object(),
                    runtime,
                    "Speel Black",
                    play=True,
                )
            )
        finally:
            self.processor.process_text_with_assist = original_assist
            self.processor.play_from_intent = original_play

        self.assertEqual(runtime.updates[0], {"last_text": "Speel Black", "last_error": None})
        self.assertEqual(runtime.last_intent["type"], "search")
        self.assertEqual(
            runtime.last_dj_text,
            "Daar is Pearl Jam, met Black. Van Ten; zet 'm maar lekker open.",
        )
        self.assertEqual(runtime.last_playback["resolved_media"]["title"], "Black")
        self.assertEqual(result["playback"]["resolved_media"]["artist"], "Pearl Jam")

    def test_process_text_command_uses_festival_style_for_resolved_track(self) -> None:
        async def assist(hass, user_text, conf):
            return {
                "type": "search",
                "spotify_search_query": user_text,
                "dj_announcement": "Daar gaan we.",
            }

        async def play(hass, runtime, intent, conf):
            return {
                "device_response": {
                    "playback": {
                        "track_name": "Alive",
                        "artist": "Pearl Jam",
                    }
                }
            }

        original_assist = self.processor.process_text_with_assist
        original_play = self.processor.play_from_intent
        self.processor.process_text_with_assist = assist
        self.processor.play_from_intent = play
        runtime = Runtime()
        runtime.config = {
            "dj_style": "festival",
            "tts_language": "nl",
        }
        try:
            result = asyncio.run(
                self.processor.process_text_command(
                    object(),
                    runtime,
                    "ik wil pearl jam starten",
                    play=True,
                )
            )
        finally:
            self.processor.process_text_with_assist = original_assist
            self.processor.play_from_intent = original_play

        self.assertEqual(
            result["dj_text"],
            "Handen omhoog: Alive van Pearl Jam. Dit is er eentje om wakker van te worden.",
        )

    def test_process_text_command_keeps_intent_when_playback_fails(self) -> None:
        async def assist(hass, user_text, conf):
            return {
                "type": "search",
                "spotify_search_query": user_text,
                "dj_announcement": "Daar gaan we.",
            }

        async def play(hass, runtime, intent, conf):
            raise RuntimeError("Spotify failed")

        original_assist = self.processor.process_text_with_assist
        original_play = self.processor.play_from_intent
        self.processor.process_text_with_assist = assist
        self.processor.play_from_intent = play
        runtime = Runtime()
        try:
            with self.assertRaisesRegex(RuntimeError, "Spotify failed"):
                asyncio.run(
                    self.processor.process_text_command(
                        object(),
                        runtime,
                        "ik wil pearl jam starten",
                        play=True,
                    )
                )
        finally:
            self.processor.process_text_with_assist = original_assist
            self.processor.play_from_intent = original_play

        self.assertEqual(runtime.last_text, "ik wil pearl jam starten")
        self.assertEqual(runtime.last_intent["type"], "search")
        self.assertEqual(
            runtime.last_intent["spotify_search_query"],
            "ik wil pearl jam starten",
        )


if __name__ == "__main__":
    unittest.main()
