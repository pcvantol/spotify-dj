from __future__ import annotations

import importlib
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

    def test_djconnect_assist_prompt_requests_fun_fact(self) -> None:
        prompt = self.pipeline._djconnect_assist_prompt(
            "Speel Black van Pearl Jam",
            "nl-NL",
        )

        self.assertIn("leuk feitje", prompt)
        self.assertIn("klassieke Nederlandse radio-DJ", prompt)
        self.assertIn("artiest", prompt)
        self.assertIn("nummer", prompt)
        self.assertIn("Speel Black van Pearl Jam", prompt)

    def test_djconnect_assist_prompt_applies_dj_style(self) -> None:
        prompt = self.pipeline._djconnect_assist_prompt(
            "Play Pearl Jam",
            "en",
            "minimal",
        )

        self.assertIn("very short and functional", prompt)
        self.assertIn("Play Pearl Jam", prompt)

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


if __name__ == "__main__":
    unittest.main()
