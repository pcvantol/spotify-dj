from __future__ import annotations

import importlib
import asyncio
from pathlib import Path
import sys
import types
import unittest


def install_pipeline_stubs() -> None:
    if "homeassistant.core" in sys.modules:
        return
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = core
    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [
        str(Path(__file__).resolve().parents[1] / "custom_components" / "djconnect")
    ]
    sys.modules["custom_components.djconnect"] = package


class AssistPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_pipeline_stubs()
        cls.pipeline = importlib.import_module("custom_components.djconnect.pipeline")

    def test_intent_from_assist_response_uses_djconnect_data(self) -> None:
        intent = self.pipeline._intent_from_assist_response(
            {
                "response": {
                    "response_type": "action_done",
                    "data": {
                        "djconnect": {
                            "type": "track",
                            "title": "Black",
                            "artist": "Pearl Jam",
                            "spotify_search_query": "Pearl Jam Black",
                            "dj_announcement": "Pearl Jam staat klaar.",
                        }
                    },
                }
            },
            "Speel Black van Pearl Jam",
        )

        self.assertEqual(intent["type"], "track")
        self.assertEqual(intent["artist"], "Pearl Jam")
        self.assertEqual(intent["spotify_search_query"], "Pearl Jam Black")
        self.assertEqual(intent["dj_announcement"], "Pearl Jam staat klaar.")

    def test_djconnect_assist_prompt_focuses_on_command_parsing(self) -> None:
        prompt = self.pipeline._djconnect_assist_prompt(
            "Speel Black van Pearl Jam",
            "nl-NL",
        )

        self.assertIn("Bepaal de artiest", prompt)
        self.assertIn("artiest", prompt)
        self.assertIn("Speel Black van Pearl Jam", prompt)
        self.assertNotIn("Noem waar mogelijk", prompt)
        self.assertNotIn("leuk feitje", prompt)

    def test_djconnect_assist_prompt_does_not_include_custom_response_prompt(self) -> None:
        prompt = self.pipeline._djconnect_assist_prompt(
            "Play Pearl Jam",
            "en",
        )

        self.assertNotIn("DJ response prompt", prompt)
        self.assertIn("Play Pearl Jam", prompt)

    def test_generate_dj_response_with_assist_uses_custom_response_prompt(self) -> None:
        calls = []

        class Services:
            async def async_call(self, domain, service, data, **kwargs):
                calls.append((domain, service, data, kwargs))
                return {
                    "response": {
                        "speech": {"plain": {"speech": "Arrr, Pearl Jam op de draaitafel!"}}
                    }
                }

        hass = types.SimpleNamespace(services=Services())
        text = asyncio.run(
            self.pipeline.generate_dj_response_with_assist(
                hass,
                media={"artist": "Pearl Jam", "uri": "spotify:artist:pearl-jam"},
                fallback_text="Daar is Pearl Jam.",
                conf={
                    "dj_response_prompt": "Sound like a pirate DJ.",
                    "tts_language": "nl-NL",
                },
            )
        )

        self.assertEqual(text, "Arrr, Pearl Jam op de draaitafel!")
        self.assertIn("Sound like a pirate DJ.", calls[0][2]["text"])

    def test_intent_from_djconnect_data_uses_speech_as_dj_response(self) -> None:
        intent = self.pipeline._intent_from_assist_response(
            {
                "response": {
                    "response_type": "query_answer",
                    "speech": {"plain": {"speech": "Ik zet Pearl Jam voor je klaar."}},
                    "data": {"djconnect": {"type": "search"}},
                }
            },
            "Speel Pearl Jam",
        )

        self.assertEqual(intent["type"], "search")
        self.assertEqual(intent["spotify_search_query"], "Speel Pearl Jam")
        self.assertEqual(intent["dj_announcement"], "Ik zet Pearl Jam voor je klaar.")

    def test_generic_assist_music_refusal_is_not_used_as_dj_response(self) -> None:
        intent = self.pipeline._intent_from_assist_response(
            {
                "response": {
                    "response_type": "query_answer",
                    "speech": {
                        "plain": {
                            "speech": (
                                "Ik kan geen muziek afspelen. Ik kan alleen apparaten "
                                "in je huis bedienen, zoals lampen, gordijnen en sensoren."
                            )
                        }
                    },
                    "data": {},
                }
            },
            "Speel Pearl Jam",
        )

        self.assertEqual(intent["type"], "search")
        self.assertEqual(intent["spotify_search_query"], "Speel Pearl Jam")
        self.assertEqual(intent["dj_announcement"], "Daar gaan we. Ik zet hem voor je klaar.")

    def test_intent_from_assist_response_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Niet begrepen"):
            self.pipeline._intent_from_assist_response(
                {
                    "response": {
                        "response_type": "error",
                        "speech": {"plain": {"speech": "Niet begrepen"}},
                    }
                },
                "Speel iets",
            )

    def test_assist_prompt_device_lookup_error_falls_back_to_search_intent(self) -> None:
        intent = self.pipeline._intent_from_assist_response(
            {
                "response": {
                    "response_type": "error",
                    "speech": {
                        "plain": {
                            "speech": (
                                "Sorry, ik kan geen apparaat vinden met de naam "
                                "Verwerk deze DJConnect muziekopdracht en maak waar mogelijk "
                                "djconnect intentdata"
                            )
                        }
                    },
                }
            },
            "Speel Black van Pearl Jam",
        )

        self.assertEqual(intent["intent"], "play_music")
        self.assertEqual(intent["type"], "search")
        self.assertEqual(intent["spotify_search_query"], "Speel Black van Pearl Jam")
        self.assertEqual(intent["dj_announcement"], "Daar gaan we. Ik zet hem voor je klaar.")

    def test_prompt_leak_device_lookup_error_falls_back_to_original_command(self) -> None:
        intent = self.pipeline._intent_from_assist_response(
            {
                "response": {
                    "response_type": "error",
                    "speech": {
                        "plain": {
                            "speech": (
                                "Sorry, ik kan Nederlands Noem waar mogelijk de artiest "
                                "en/of het nummer Opdracht Metallica niet vinden"
                            )
                        }
                    },
                }
            },
            "Metallica",
        )

        self.assertEqual(intent["type"], "search")
        self.assertEqual(intent["spotify_search_query"], "Metallica")


if __name__ == "__main__":
    unittest.main()
