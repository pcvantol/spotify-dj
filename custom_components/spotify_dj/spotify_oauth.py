from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any

from aiohttp import ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_SPOTIFY_CALLBACK

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


def create_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def create_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_redirect_uri(base_url: str) -> str:
    return base_url.rstrip("/") + API_SPOTIFY_CALLBACK


def build_authorize_url(client_id: str, redirect_uri: str, scopes: str, state: str, code_verifier: str) -> str:
    from urllib.parse import urlencode
    query = urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "code_challenge_method": "S256",
        "code_challenge": create_code_challenge(code_verifier),
        "state": state,
        "scope": scopes,
    })
    return f"{SPOTIFY_AUTHORIZE_URL}?{query}"


async def exchange_code_for_refresh_token(
    hass: HomeAssistant,
    *,
    client_id: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    session = async_get_clientsession(hass)
    data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    async with session.post(SPOTIFY_TOKEN_URL, data=data, timeout=ClientTimeout(total=20)) as resp:
        body = await resp.json(content_type=None)
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"Spotify token exchange failed HTTP {resp.status}: {body}")
        if not body.get("refresh_token"):
            raise RuntimeError("Spotify token response did not contain a refresh_token")
        return body
