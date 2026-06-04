from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant


class OpenAIError(RuntimeError):
    pass


def _disabled() -> OpenAIError:
    return OpenAIError("Direct OpenAI API is disabled in SpotifyDJ; use HA Assist/TTS instead")


async def chat_json(hass: HomeAssistant, api_key: str, model: str, system: str, user: str) -> dict[str, Any]:
    raise _disabled()


async def transcribe_wav(hass: HomeAssistant, api_key: str, model: str, wav: bytes, language: str = "nl") -> str:
    raise _disabled()


async def speech_wav(hass: HomeAssistant, api_key: str, model: str, voice: str, text: str, instructions: str | None = None) -> bytes:
    raise _disabled()
