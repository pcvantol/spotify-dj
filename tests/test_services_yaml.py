from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "custom_components" / "djconnect" / "services.yaml"


class ServicesYamlTest(unittest.TestCase):
    def test_developer_actions_are_documented(self) -> None:
        text = SERVICES.read_text()
        compact_text = " ".join(text.split())

        for service in (
            "test_parse",
            "test_tts",
            "test_command",
            "test_ptt_text",
            "start_spotify_oauth",
            "device_command",
            "refresh_device_info",
        ):
            with self.subTest(service=service):
                self.assertIn(f"{service}:", text)

        self.assertIn("Developer test", text)
        self.assertIn("Developer helper", text)
        self.assertIn("temporary WAV or MP3 audio_url", text)
        self.assertIn("start exactly after STT conversion", compact_text)
        self.assertIn("Spotify search/playback", compact_text)
        self.assertIn("/api/djconnect/spotify/callback", text)
        self.assertNotIn("/api/djconnect/spotify_callback", text)
        self.assertNotIn("stuur", text.lower())
        self.assertNotIn("zonder Spotify playback", text)

    def test_test_command_documents_play_flag(self) -> None:
        text = SERVICES.read_text()

        self.assertIn("command_text:", text)
        self.assertIn("dj_response_text:", text)
        self.assertNotIn("\n    text:\n      name:", text)
        self.assertIn("play:", text)
        self.assertIn("Start playback", text)
        self.assertIn("without starting Spotify playback", text)


if __name__ == "__main__":
    unittest.main()
