from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_DEVICE_TOKEN,
    CONF_HA_EXTERNAL_URL,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    DEFAULT_SPOTIFY_CLIENT_ID,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
    DOMAIN,
)
from .spotify_oauth import (
    build_authorize_url,
    build_redirect_uri,
    create_code_verifier,
    missing_spotify_scopes,
)

FIXABLE_SPOTIFY_ISSUES = {
    "missing_spotify_refresh_token",
    "missing_spotify_oauth_scopes",
    "spotify_refresh_token_revoked",
}


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
    if not entry.data.get(CONF_SPOTIFY_REFRESH_TOKEN):
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"{entry.entry_id}_missing_spotify_refresh_token",
            data={"entry_id": entry.entry_id},
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_spotify_refresh_token",
        )
    if missing_spotify_scopes(entry.data.get(CONF_SPOTIFY_SCOPES)):
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"{entry.entry_id}_missing_spotify_oauth_scopes",
            data={"entry_id": entry.entry_id},
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_spotify_oauth_scopes",
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a Repairs fix flow for Spotify reauthorization."""
    issue_key = _issue_key(issue_id)
    if issue_key in FIXABLE_SPOTIFY_ISSUES:
        return SpotifyOAuthRepairFlow(hass, issue_id, data or {})
    return SpotifyOAuthRepairFlow(hass, issue_id, data or {})


class SpotifyOAuthRepairFlow(RepairsFlow):
    """Repair flow that guides users through Spotify OAuth reauthorization."""

    def __init__(
        self,
        hass: HomeAssistant,
        issue_id: str,
        data: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.issue_id = issue_id
        self.data = data
        self._state = ""
        self._authorize_url = ""
        self._original_refresh_token = ""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start or complete Spotify OAuth repair."""
        entry = _entry_from_issue(self.hass, self.issue_id, self.data)
        if entry is None:
            return self.async_abort(reason="entry_not_found")
        if not self._authorize_url:
            self._original_refresh_token = str(
                entry.data.get(CONF_SPOTIFY_REFRESH_TOKEN) or ""
            )
            self._authorize_url = await _prepare_spotify_repair_oauth(self.hass, entry)
            external_step = getattr(self, "async_external_step", None)
            if callable(external_step):
                return external_step(
                    step_id="init",
                    url=self._authorize_url,
                    description_placeholders={"authorize_url": self._authorize_url},
                )
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                description_placeholders={"authorize_url": self._authorize_url},
            )
        if user_input is not None:
            current_refresh_token = str(
                entry.data.get(CONF_SPOTIFY_REFRESH_TOKEN) or ""
            )
            token_changed = (
                bool(current_refresh_token)
                and current_refresh_token != self._original_refresh_token
            )
            token_was_missing = bool(current_refresh_token) and not self._original_refresh_token
            if token_changed or token_was_missing:
                _delete_spotify_reauth_issues(self.hass, entry.entry_id)
                return self.async_create_entry(title="", data={})
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                errors={"base": "oauth_not_completed"},
                description_placeholders={"authorize_url": self._authorize_url},
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders={"authorize_url": self._authorize_url},
        )


def _issue_key(issue_id: str) -> str:
    for suffix in FIXABLE_SPOTIFY_ISSUES:
        if issue_id.endswith(f"_{suffix}") or issue_id == suffix:
            return suffix
    return issue_id


def _entry_from_issue(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any],
) -> ConfigEntry | None:
    entry_id = str(data.get("entry_id") or "")
    if not entry_id:
        for suffix in FIXABLE_SPOTIFY_ISSUES:
            marker = f"_{suffix}"
            if issue_id.endswith(marker):
                entry_id = issue_id[: -len(marker)]
                break
    getter = getattr(getattr(hass, "config_entries", None), "async_get_entry", None)
    return getter(entry_id) if callable(getter) and entry_id else None


async def _prepare_spotify_repair_oauth(hass: HomeAssistant, entry: ConfigEntry) -> str:
    client_id = str(
        entry.data.get(CONF_SPOTIFY_CLIENT_ID) or DEFAULT_SPOTIFY_CLIENT_ID
    ).strip()
    external_url = str(entry.data.get(CONF_HA_EXTERNAL_URL) or "").strip().rstrip("/")
    if not external_url:
        external_url = str(getattr(getattr(hass, "config", None), "external_url", "") or "").strip().rstrip("/")
    redirect_uri = build_redirect_uri(external_url)
    state = secrets.token_urlsafe(24)
    code_verifier = create_code_verifier()
    scopes = DEFAULT_SPOTIFY_SCOPES
    pending = hass.data.setdefault(DOMAIN, {}).setdefault("spotify_oauth_pending", {})
    pending[state] = {
        "entry_id": entry.entry_id,
        "client_id": client_id,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "market": entry.data.get(CONF_SPOTIFY_MARKET, DEFAULT_SPOTIFY_MARKET),
        "scopes": scopes,
        "repair_issue_id": f"{DOMAIN}:{entry.entry_id}",
    }
    return build_authorize_url(client_id, redirect_uri, scopes, state, code_verifier)


def _delete_spotify_reauth_issues(hass: HomeAssistant, entry_id: str) -> None:
    for suffix in FIXABLE_SPOTIFY_ISSUES:
        try:
            ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_{suffix}")
        except Exception:  # noqa: BLE001
            pass
