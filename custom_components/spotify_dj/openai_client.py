from __future__ import annotations

import json
from typing import Any

from aiohttp import FormData, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

OPENAI_BASE = "https://api.openai.com/v1"

class OpenAIError(RuntimeError):
    pass

def _headers(api_key: str, content_type: str | None = "application/json") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers

async def chat_json(hass: HomeAssistant, api_key: str, model: str, system: str, user: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.35,
    }
    session = async_get_clientsession(hass)
    async with session.post(f"{OPENAI_BASE}/chat/completions", headers=_headers(api_key), json=payload, timeout=ClientTimeout(total=45)) as resp:
        body = await resp.text()
        if resp.status >= 400:
            raise OpenAIError(f"OpenAI chat failed {resp.status}: {body[:500]}")
        data = json.loads(body)
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)

async def transcribe_wav(hass: HomeAssistant, api_key: str, model: str, wav: bytes, language: str = "nl") -> str:
    data = FormData()
    data.add_field("model", model)
    data.add_field("language", language)
    data.add_field("file", wav, filename="speech.wav", content_type="audio/wav")
    session = async_get_clientsession(hass)
    async with session.post(f"{OPENAI_BASE}/audio/transcriptions", headers=_headers(api_key, None), data=data, timeout=ClientTimeout(total=90)) as resp:
        body = await resp.text()
        if resp.status >= 400:
            raise OpenAIError(f"OpenAI STT failed {resp.status}: {body[:500]}")
        result = json.loads(body)
    return (result.get("text") or "").strip()

async def speech_wav(hass: HomeAssistant, api_key: str, model: str, voice: str, text: str, instructions: str | None = None) -> bytes:
    payload = {"model": model, "voice": voice, "input": text, "response_format": "wav"}
    if instructions:
        payload["instructions"] = instructions
    session = async_get_clientsession(hass)
    async with session.post(f"{OPENAI_BASE}/audio/speech", headers=_headers(api_key), json=payload, timeout=ClientTimeout(total=90)) as resp:
        body = await resp.read()
        if resp.status >= 400:
            try:
                msg = body.decode("utf-8", "ignore")
            except Exception:
                msg = repr(body[:200])
            raise OpenAIError(f"OpenAI TTS failed {resp.status}: {msg[:500]}")
        return body
