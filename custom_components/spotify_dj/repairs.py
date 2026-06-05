from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_DEVICE_TOKEN,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_SCOPES,
    DOMAIN,
)
from .spotify_oauth import missing_spotify_scopes


async def async_create_fixable_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if not entry.data.get(CONF_DEVICE_TOKEN):
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"{entry.entry_id}_missing_device_token",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_device_token",
        )
    if not entry.data.get(CONF_SPOTIFY_CLIENT_ID):
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"{entry.entry_id}_missing_spotify_client_id",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_spotify_client_id",
        )
    if missing_spotify_scopes(entry.data.get(CONF_SPOTIFY_SCOPES)):
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"{entry.entry_id}_missing_spotify_oauth_scopes",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_spotify_oauth_scopes",
        )
