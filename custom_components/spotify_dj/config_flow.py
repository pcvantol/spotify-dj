"""Config flow for SpotifyDJ with Spotify OAuth/PKCE.

The flow is intentionally defensive so it keeps loading on HA even while the
firmware/device side is under active development.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ALLOW_OTA_ON_BATTERY,
    CONF_ASSIST_PIPELINE_ID,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TOKEN,
    CONF_DJ_PROFILE,
    CONF_DJ_STYLE,
    CONF_FIRMWARE_ASSET_PREFIX,
    CONF_FIRMWARE_CHANNEL,
    CONF_FIRMWARE_DEVICE,
    CONF_FIRMWARE_REPO,
    CONF_LIKED_PROXY,
    CONF_LOCAL_URL,
    CONF_MAX_AUDIO_BYTES,
    CONF_MIN_BATTERY_FOR_OTA,
    CONF_PAIR_CODE,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_PLAYER,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    CONF_SPOTIFY_SOURCE,
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    CONF_TTS_VOICE,
    DEFAULT_ASSIST_PIPELINE_ID,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DJ_STYLE,
    DEFAULT_FIRMWARE_ASSET_PREFIX,
    DEFAULT_FIRMWARE_CHANNEL,
    DEFAULT_FIRMWARE_DEVICE,
    DEFAULT_FIRMWARE_REPO,
    DEFAULT_MAX_AUDIO_BYTES,
    DEFAULT_MIN_BATTERY_FOR_OTA,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
    DEFAULT_TTS_ENGINE,
    DEFAULT_TTS_LANGUAGE,
    DEFAULT_TTS_VOICE,
    DJ_STYLE_NAMES,
    DJ_STYLES,
    DOMAIN,
    SPOTIFY_MY_HOME_ASSISTANT_REDIRECT_URI,
)
from .spotify_oauth import (
    build_authorize_url,
    create_code_verifier,
    exchange_code_for_refresh_token,
)

_LOGGER = logging.getLogger(__name__)


def _clean(value: Any, default: Any = "") -> Any:
    """Normalize empty form values."""
    if value is None:
        return default
    if isinstance(value, str) and value.strip() == "":
        return default
    return value


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(_clean(value, default))
    except (TypeError, ValueError):
        return default


def _extract_oauth_code(value: str) -> str:
    """Extract Spotify authorization code from a pasted full callback URL or raw code."""
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        qs = parse_qs(parsed.query)
        if qs.get("code"):
            return qs["code"][0]
    return value


def _voice_defaults(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return voice/options config with safe defaults."""
    source = data or {}
    dj_style = _clean(source.get(CONF_DJ_STYLE) or source.get(CONF_DJ_PROFILE), DEFAULT_DJ_STYLE)
    if dj_style not in DJ_STYLES:
        dj_style = DEFAULT_DJ_STYLE
    return {
        CONF_ASSIST_PIPELINE_ID: _clean(source.get(CONF_ASSIST_PIPELINE_ID), DEFAULT_ASSIST_PIPELINE_ID),
        CONF_TTS_ENGINE: _clean(source.get(CONF_TTS_ENGINE), DEFAULT_TTS_ENGINE),
        CONF_TTS_LANGUAGE: _clean(source.get(CONF_TTS_LANGUAGE), DEFAULT_TTS_LANGUAGE),
        CONF_TTS_VOICE: _clean(source.get(CONF_TTS_VOICE), DEFAULT_TTS_VOICE),
        CONF_DJ_STYLE: dj_style,
        CONF_DJ_PROFILE: dj_style,
        CONF_FIRMWARE_REPO: _clean(source.get(CONF_FIRMWARE_REPO), DEFAULT_FIRMWARE_REPO),
        CONF_FIRMWARE_ASSET_PREFIX: _clean(source.get(CONF_FIRMWARE_ASSET_PREFIX), DEFAULT_FIRMWARE_ASSET_PREFIX),
        CONF_FIRMWARE_DEVICE: _clean(source.get(CONF_FIRMWARE_DEVICE), DEFAULT_FIRMWARE_DEVICE),
        CONF_FIRMWARE_CHANNEL: _clean(source.get(CONF_FIRMWARE_CHANNEL), DEFAULT_FIRMWARE_CHANNEL),
        CONF_MAX_AUDIO_BYTES: _int(source.get(CONF_MAX_AUDIO_BYTES), DEFAULT_MAX_AUDIO_BYTES),
        CONF_ALLOW_OTA_ON_BATTERY: _bool(source.get(CONF_ALLOW_OTA_ON_BATTERY), False),
        CONF_MIN_BATTERY_FOR_OTA: _int(source.get(CONF_MIN_BATTERY_FOR_OTA), DEFAULT_MIN_BATTERY_FOR_OTA),
        CONF_SPOTIFY_PLAYER: _clean(source.get(CONF_SPOTIFY_PLAYER), ""),
        CONF_SPOTIFY_SOURCE: _clean(source.get(CONF_SPOTIFY_SOURCE), ""),
        CONF_LIKED_PROXY: _clean(source.get(CONF_LIKED_PROXY), ""),
    }


class SpotifyDJConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the SpotifyDJ config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._pairing: dict[str, Any] = {}
        self._spotify: dict[str, Any] = {}
        self._voice: dict[str, Any] = {}
        self._oauth: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Pair the LilyGO device using the displayed pair code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pair_code = str(user_input.get(CONF_PAIR_CODE, "")).strip()
            if len(pair_code) != 6 or not pair_code.isdigit():
                errors[CONF_PAIR_CODE] = "invalid_pair_code"
            else:
                # Until mDNS discovery/pair pre-registration is fully wired, the pair
                # code becomes a stable unique placeholder. The ESP will later report
                # its real device_id through status/pair endpoints.
                device_id = f"spotifydj-{pair_code}"
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                self._pairing = {
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_NAME: _clean(user_input.get(CONF_DEVICE_NAME), DEFAULT_DEVICE_NAME),
                    CONF_DEVICE_TOKEN: __import__("secrets").token_urlsafe(32),
                    CONF_LOCAL_URL: _clean(user_input.get(CONF_LOCAL_URL), ""),
                }
                return await self.async_step_spotify()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PAIR_CODE): str,
                    vol.Optional(CONF_DEVICE_NAME, default=DEFAULT_DEVICE_NAME): str,
                    vol.Optional(CONF_LOCAL_URL, default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_spotify(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect Spotify Client ID and market, then start OAuth."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client_id = str(user_input.get(CONF_SPOTIFY_CLIENT_ID, "")).strip()
            if not client_id:
                errors[CONF_SPOTIFY_CLIENT_ID] = "required"
            else:
                self._spotify = {
                    CONF_SPOTIFY_CLIENT_ID: client_id,
                    CONF_SPOTIFY_MARKET: _clean(user_input.get(CONF_SPOTIFY_MARKET), DEFAULT_SPOTIFY_MARKET),
                    CONF_SPOTIFY_SCOPES: DEFAULT_SPOTIFY_SCOPES,
                }
                return await self.async_step_spotify_oauth_start()

        return self.async_show_form(
            step_id="spotify",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SPOTIFY_CLIENT_ID): str,
                    vol.Optional(CONF_SPOTIFY_MARKET, default=DEFAULT_SPOTIFY_MARKET): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "redirect_uri": SPOTIFY_MY_HOME_ASSISTANT_REDIRECT_URI,
            },
        )

    async def async_step_spotify_oauth_start(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Launch Spotify OAuth in the browser.

        Home Assistant external-step callback behaviour can vary by install and
        reverse proxy. Therefore this flow both opens the browser and provides a
        robust fallback step where the user can paste the final callback URL/code.
        """
        code_verifier = create_code_verifier()
        state = __import__("secrets").token_urlsafe(24)
        self._oauth = {
            "code_verifier": code_verifier,
            "state": state,
            "redirect_uri": SPOTIFY_MY_HOME_ASSISTANT_REDIRECT_URI,
        }
        authorize_url = build_authorize_url(
            self._spotify[CONF_SPOTIFY_CLIENT_ID],
            SPOTIFY_MY_HOME_ASSISTANT_REDIRECT_URI,
            self._spotify.get(CONF_SPOTIFY_SCOPES, DEFAULT_SPOTIFY_SCOPES),
            state,
            code_verifier,
        )

        # Try the native HA external-step UX first. If HA does not hand the code
        # back into this flow, the next step asks for the callback URL/code.
        try:
            return self.async_external_step(step_id="spotify_oauth", url=authorize_url)
        except AttributeError:
            return await self.async_step_spotify_oauth_manual({"auth_url": authorize_url})

    async def async_step_spotify_oauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle HA external OAuth callback if HA supplies code/state."""
        code = ""
        state = ""
        if user_input:
            code = _extract_oauth_code(user_input.get("code") or user_input.get("url") or "")
            state = str(user_input.get("state") or "")

        if code:
            return await self._finish_spotify_oauth(code, state)

        # If HA returns from the external step without code details, continue to
        # the fallback form. The user can paste the final URL or only the code.
        try:
            return self.async_external_step_done(next_step_id="spotify_oauth_manual")
        except AttributeError:
            return await self.async_step_spotify_oauth_manual()

    async def async_step_spotify_oauth_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Fallback form: paste Spotify callback URL or authorization code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = _extract_oauth_code(str(user_input.get("callback_url_or_code", "")))
            if not code:
                errors["callback_url_or_code"] = "required"
            else:
                try:
                    return await self._finish_spotify_oauth(code, "")
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.exception("Spotify OAuth failed")
                    errors["base"] = "oauth_failed"

        authorize_url = build_authorize_url(
            self._spotify[CONF_SPOTIFY_CLIENT_ID],
            SPOTIFY_MY_HOME_ASSISTANT_REDIRECT_URI,
            self._spotify.get(CONF_SPOTIFY_SCOPES, DEFAULT_SPOTIFY_SCOPES),
            self._oauth.get("state") or __import__("secrets").token_urlsafe(24),
            self._oauth.get("code_verifier") or create_code_verifier(),
        )
        return self.async_show_form(
            step_id="spotify_oauth_manual",
            data_schema=vol.Schema({vol.Required("callback_url_or_code"): str}),
            errors=errors,
            description_placeholders={"authorize_url": authorize_url},
        )

    async def _finish_spotify_oauth(self, code: str, state: str = "") -> FlowResult:
        """Exchange Spotify authorization code for refresh token."""
        if state and self._oauth.get("state") and state != self._oauth["state"]:
            raise RuntimeError("Spotify OAuth state mismatch")

        token = await exchange_code_for_refresh_token(
            self.hass,
            client_id=self._spotify[CONF_SPOTIFY_CLIENT_ID],
            code=code,
            code_verifier=self._oauth["code_verifier"],
            redirect_uri=SPOTIFY_MY_HOME_ASSISTANT_REDIRECT_URI,
        )
        self._spotify[CONF_SPOTIFY_REFRESH_TOKEN] = token["refresh_token"]
        return await self.async_step_voice()

    async def async_step_voice(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect optional voice settings. Empty fields are allowed."""
        if user_input is not None:
            data: dict[str, Any] = {}
            data.update(self._pairing)
            data.update(self._spotify)
            data.update(_voice_defaults(user_input))
            return self.async_create_entry(
                title=data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
                data=data,
            )

        return self.async_show_form(
            step_id="voice",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ASSIST_PIPELINE_ID, default=""): str,
                    vol.Optional(CONF_TTS_ENGINE, default=DEFAULT_TTS_ENGINE): str,
                    vol.Optional(CONF_TTS_LANGUAGE, default=DEFAULT_TTS_LANGUAGE): str,
                    vol.Optional(CONF_TTS_VOICE, default=""): str,
                    vol.Optional(CONF_DJ_STYLE, default=DEFAULT_DJ_STYLE): vol.In(DJ_STYLE_NAMES),
                    vol.Optional(CONF_SPOTIFY_PLAYER, default=""): str,
                    vol.Optional(CONF_SPOTIFY_SOURCE, default=""): str,
                    vol.Optional(CONF_LIKED_PROXY, default=""): str,
                    vol.Optional(CONF_FIRMWARE_REPO, default=DEFAULT_FIRMWARE_REPO): str,
                    vol.Optional(CONF_FIRMWARE_ASSET_PREFIX, default=DEFAULT_FIRMWARE_ASSET_PREFIX): str,
                    vol.Optional(CONF_FIRMWARE_DEVICE, default=DEFAULT_FIRMWARE_DEVICE): str,
                    vol.Optional(CONF_FIRMWARE_CHANNEL, default=DEFAULT_FIRMWARE_CHANNEL): str,
                    vol.Optional(CONF_MAX_AUDIO_BYTES, default=DEFAULT_MAX_AUDIO_BYTES): int,
                    vol.Optional(CONF_ALLOW_OTA_ON_BATTERY, default=False): bool,
                    vol.Optional(CONF_MIN_BATTERY_FOR_OTA, default=DEFAULT_MIN_BATTERY_FOR_OTA): int,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "SpotifyDJOptionsFlow":
        """Create options flow."""
        return SpotifyDJOptionsFlow(config_entry)


class SpotifyDJOptionsFlow(config_entries.OptionsFlow):
    """Handle SpotifyDJ options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            return self.async_create_entry(title="", data=_voice_defaults(user_input))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ASSIST_PIPELINE_ID, default=current.get(CONF_ASSIST_PIPELINE_ID, "")): str,
                    vol.Optional(CONF_TTS_ENGINE, default=current.get(CONF_TTS_ENGINE, DEFAULT_TTS_ENGINE)): str,
                    vol.Optional(CONF_TTS_LANGUAGE, default=current.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE)): str,
                    vol.Optional(CONF_TTS_VOICE, default=current.get(CONF_TTS_VOICE, "")): str,
                    vol.Optional(CONF_DJ_STYLE, default=current.get(CONF_DJ_STYLE, current.get(CONF_DJ_PROFILE, DEFAULT_DJ_STYLE))): vol.In(DJ_STYLE_NAMES),
                    vol.Optional(CONF_SPOTIFY_PLAYER, default=current.get(CONF_SPOTIFY_PLAYER, "")): str,
                    vol.Optional(CONF_SPOTIFY_SOURCE, default=current.get(CONF_SPOTIFY_SOURCE, "")): str,
                    vol.Optional(CONF_LIKED_PROXY, default=current.get(CONF_LIKED_PROXY, "")): str,
                    vol.Optional(CONF_FIRMWARE_REPO, default=current.get(CONF_FIRMWARE_REPO, DEFAULT_FIRMWARE_REPO)): str,
                    vol.Optional(CONF_FIRMWARE_ASSET_PREFIX, default=current.get(CONF_FIRMWARE_ASSET_PREFIX, DEFAULT_FIRMWARE_ASSET_PREFIX)): str,
                    vol.Optional(CONF_FIRMWARE_DEVICE, default=current.get(CONF_FIRMWARE_DEVICE, DEFAULT_FIRMWARE_DEVICE)): str,
                    vol.Optional(CONF_FIRMWARE_CHANNEL, default=current.get(CONF_FIRMWARE_CHANNEL, DEFAULT_FIRMWARE_CHANNEL)): str,
                    vol.Optional(CONF_MAX_AUDIO_BYTES, default=current.get(CONF_MAX_AUDIO_BYTES, DEFAULT_MAX_AUDIO_BYTES)): int,
                    vol.Optional(CONF_ALLOW_OTA_ON_BATTERY, default=current.get(CONF_ALLOW_OTA_ON_BATTERY, False)): bool,
                    vol.Optional(CONF_MIN_BATTERY_FOR_OTA, default=current.get(CONF_MIN_BATTERY_FOR_OTA, DEFAULT_MIN_BATTERY_FOR_OTA)): int,
                }
            ),
        )
