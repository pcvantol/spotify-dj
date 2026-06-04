from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest


def install_openai_stubs() -> None:
    if "homeassistant.core" in sys.modules:
        return
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = core


class LegacyOpenAIClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_openai_stubs()
        cls.openai_client = importlib.import_module(
            "custom_components.spotify_dj.openai_client"
        )

    def test_chat_json_is_disabled(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Direct OpenAI API is disabled"):
            asyncio.run(
                self.openai_client.chat_json(
                    object(),
                    "api-key",
                    "model",
                    "system",
                    "user",
                )
            )


if __name__ == "__main__":
    unittest.main()
