"""Config flow for SpotifyDJ."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ASSIST_PIPELINE_ID,
    CONF_DEVICE_NAME,
    CONF_DJ_STYLE,
    CONF_FIRMWARE_CHANNEL,
    CONF_FIRMWARE_REPO,
    CONF_PAIR_CODE,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    CONF_TTS_VOICE,
    DEFAULT_ASSIST_PIPELINE_ID,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DJ_STYLE,
    DEFAULT_FIRMWARE_CHANNEL,
    DEFAULT_FIRMWARE_REPO,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_TTS_ENGINE,
    DEFAULT_TTS_LANGUAGE,
    DEFAULT_TTS_VOICE,
    DJ_STYLE_NAMES,
    DJ_STYLES,
    DOMAIN,
    FIRMWARE_CHANNELS,
)

_LOGGER = logging.getLogger(__name__)


def _clean_optional(value: Any, default: Any = None) -> Any:
    """Normalize empty form values."""
    if value is None:
        return default
    if isinstance(value, str) and value.strip() == "":
        return default
    return value


class SpotifyDJConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SpotifyDJ."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._pair_data: dict[str, Any] = {}
        self._spotify_data: dict[str, Any] = {}
        self._voice_data: dict[str, Any] = {}

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Start pairing flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pair_code = str(user_input.get(CONF_PAIR_CODE, "")).strip()
            device_name = str(
                user_input.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)
                or DEFAULT_DEVICE_NAME
            ).strip()

            if not pair_code:
                errors[CONF_PAIR_CODE] = "required"
            else:
                self._pair_data = {
                    CONF_PAIR_CODE: pair_code,
                    CONF_DEVICE_NAME: device_name or DEFAULT_DEVICE_NAME,
                }
                return await self.async_step_spotify()

        schema = vol.Schema(
            {
                vol.Required(CONF_PAIR_CODE): str,
                vol.Optional(
                    CONF_DEVICE_NAME,
                    default=DEFAULT_DEVICE_NAME,
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "name": DEFAULT_DEVICE_NAME,
            },
        )

    async def async_step_spotify(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Collect Spotify app settings.

        This step intentionally asks only for Client ID.
        PKCE OAuth can be attached after this step, or implemented in a later
        async_external_step without exposing refresh tokens in the UI.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            client_id = str(user_input.get(CONF_SPOTIFY_CLIENT_ID, "")).strip()
            market = str(
                user_input.get(CONF_SPOTIFY_MARKET, DEFAULT_SPOTIFY_MARKET)
                or DEFAULT_SPOTIFY_MARKET
            ).strip()

            if not client_id:
                errors[CONF_SPOTIFY_CLIENT_ID] = "required"
            else:
                self._spotify_data = {
                    CONF_SPOTIFY_CLIENT_ID: client_id,
                    CONF_SPOTIFY_MARKET: market or DEFAULT_SPOTIFY_MARKET,
                }
                return await self.async_step_voice()

        schema = vol.Schema(
            {
                vol.Required(CONF_SPOTIFY_CLIENT_ID): str,
                vol.Optional(
                    CONF_SPOTIFY_MARKET,
                    default=DEFAULT_SPOTIFY_MARKET,
                ): str,
            }
        )

        return self.async_show_form(
            step_id="spotify",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_voice(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Collect voice settings with safe defaults."""
        errors: dict[str, str] = {}

        if user_input is not None:
            dj_style = _clean_optional(
                user_input.get(CONF_DJ_STYLE),
                DEFAULT_DJ_STYLE,
            )

            if dj_style not in DJ_STYLES:
                dj_style = DEFAULT_DJ_STYLE

            self._voice_data = {
                CONF_ASSIST_PIPELINE_ID: _clean_optional(
                    user_input.get(CONF_ASSIST_PIPELINE_ID),
                    DEFAULT_ASSIST_PIPELINE_ID,
                ),
                CONF_TTS_ENGINE: _clean_optional(
                    user_input.get(CONF_TTS_ENGINE),
                    DEFAULT_TTS_ENGINE,
                ),
                CONF_TTS_LANGUAGE: _clean_optional(
                    user_input.get(CONF_TTS_LANGUAGE),
                    DEFAULT_TTS_LANGUAGE,
                ),
                CONF_TTS_VOICE: _clean_optional(
                    user_input.get(CONF_TTS_VOICE),
                    DEFAULT_TTS_VOICE,
                ),
                CONF_DJ_STYLE: dj_style,
                CONF_FIRMWARE_REPO: _clean_optional(
                    user_input.get(CONF_FIRMWARE_REPO),
                    DEFAULT_FIRMWARE_REPO,
                ),
                CONF_FIRMWARE_CHANNEL: _clean_optional(
                    user_input.get(CONF_FIRMWARE_CHANNEL),
                    DEFAULT_FIRMWARE_CHANNEL,
                ),
            }

            data = {}
            data.update(self._pair_data)
            data.update(self._spotify_data)
            data.update(self._voice_data)

            title = data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)

            return self.async_create_entry(
                title=title,
                data=data,
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ASSIST_PIPELINE_ID,
                    default="",
                ): str,
                vol.Optional(
                    CONF_TTS_ENGINE,
                    default=DEFAULT_TTS_ENGINE,
                ): str,
                vol.Optional(
                    CONF_TTS_LANGUAGE,
                    default=DEFAULT_TTS_LANGUAGE,
                ): str,
                vol.Optional(
                    CONF_TTS_VOICE,
                    default="",
                ): str,
                vol.Optional(
                    CONF_DJ_STYLE,
                    default=DEFAULT_DJ_STYLE,
                ): vol.In(DJ_STYLE_NAMES),
                vol.Optional(
                    CONF_FIRMWARE_REPO,
                    default=DEFAULT_FIRMWARE_REPO,
                ): str,
                vol.Optional(
                    CONF_FIRMWARE_CHANNEL,
                    default=DEFAULT_FIRMWARE_CHANNEL,
                ): vol.In(FIRMWARE_CHANNELS),
            }
        )

        return self.async_show_form(
            step_id="voice",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SpotifyDJOptionsFlow:
        """Create the options flow."""
        return SpotifyDJOptionsFlow(config_entry)


class SpotifyDJOptionsFlow(config_entries.OptionsFlow):
    """Handle SpotifyDJ options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage options."""
        current = {
            **self.config_entry.data,
            **self.config_entry.options,
        }

        if user_input is not None:
            dj_style = _clean_optional(
                user_input.get(CONF_DJ_STYLE),
                DEFAULT_DJ_STYLE,
            )

            if dj_style not in DJ_STYLES:
                dj_style = DEFAULT_DJ_STYLE

            options = {
                CONF_ASSIST_PIPELINE_ID: _clean_optional(
                    user_input.get(CONF_ASSIST_PIPELINE_ID),
                    DEFAULT_ASSIST_PIPELINE_ID,
                ),
                CONF_TTS_ENGINE: _clean_optional(
                    user_input.get(CONF_TTS_ENGINE),
                    DEFAULT_TTS_ENGINE,
                ),
                CONF_TTS_LANGUAGE: _clean_optional(
                    user_input.get(CONF_TTS_LANGUAGE),
                    DEFAULT_TTS_LANGUAGE,
                ),
                CONF_TTS_VOICE: _clean_optional(
                    user_input.get(CONF_TTS_VOICE),
                    DEFAULT_TTS_VOICE,
                ),
                CONF_DJ_STYLE: dj_style,
                CONF_FIRMWARE_REPO: _clean_optional(
                    user_input.get(CONF_FIRMWARE_REPO),
                    DEFAULT_FIRMWARE_REPO,
                ),
                CONF_FIRMWARE_CHANNEL: _clean_optional(
                    user_input.get(CONF_FIRMWARE_CHANNEL),
                    DEFAULT_FIRMWARE_CHANNEL,
                ),
            }

            return self.async_create_entry(
                title="",
                data=options,
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ASSIST_PIPELINE_ID,
                    default=current.get(CONF_ASSIST_PIPELINE_ID) or "",
                ): str,
                vol.Optional(
                    CONF_TTS_ENGINE,
                    default=current.get(CONF_TTS_ENGINE, DEFAULT_TTS_ENGINE),
                ): str,
                vol.Optional(
                    CONF_TTS_LANGUAGE,
                    default=current.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE),
                ): str,
                vol.Optional(
                    CONF_TTS_VOICE,
                    default=current.get(CONF_TTS_VOICE) or "",
                ): str,
                vol.Optional(
                    CONF_DJ_STYLE,
                    default=current.get(CONF_DJ_STYLE, DEFAULT_DJ_STYLE),
                ): vol.In(DJ_STYLE_NAMES),
                vol.Optional(
                    CONF_FIRMWARE_REPO,
                    default=current.get(CONF_FIRMWARE_REPO, DEFAULT_FIRMWARE_REPO),
                ): str,
                vol.Optional(
                    CONF_FIRMWARE_CHANNEL,
                    default=current.get(
                        CONF_FIRMWARE_CHANNEL,
                        DEFAULT_FIRMWARE_CHANNEL,
                    ),
                ): vol.In(FIRMWARE_CHANNELS),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )