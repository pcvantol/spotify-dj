from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant

from .const import CONF_OPENAI_API_KEY, CONF_OPENAI_CHAT_MODEL, CONF_DJ_STYLE, DEFAULT_CHAT_MODEL, DEFAULT_DJ_STYLE
from .openai_client import chat_json

_LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Je bent SpotifyDJ, een Nederlandse AI radio-dj en muziek-intent parser voor Home Assistant.
Zet de muziekaanvraag om naar strikt geldige JSON. Geen markdown, geen uitleg.

Schema:
{
  "intent": "play_music",
  "type": "track|album|artist|playlist|liked|latest_album|search",
  "artist": string|null,
  "title": string|null,
  "playlist": string|null,
  "query": string,
  "spotify_search_query": string,
  "dj_announcement": string
}

Regels:
- Gebruik Nederlands.
- Houd dj_announcement kort: maximaal 2 zinnen, 4 tot 10 seconden gesproken.
- Stijl: {dj_style}
- Imiteer geen specifieke bestaande persoon en gebruik geen echte station-jingles.
- Als iemand vraagt om "nieuwste album van <artiest>", gebruik type latest_album en artist.
- Als iemand vraagt om favoriete nummers/likes/liked songs, gebruik type liked.
- Als iemand een playlist noemt, gebruik type playlist en zet playlist op de naam.
- spotify_search_query moet bruikbaar zijn voor Spotify search.
""".strip()

async def parse_music_request(hass: HomeAssistant, user_text: str, conf: dict) -> dict:
    api_key = conf[CONF_OPENAI_API_KEY]
    model = conf.get(CONF_OPENAI_CHAT_MODEL, DEFAULT_CHAT_MODEL)
    style = conf.get(CONF_DJ_STYLE, DEFAULT_DJ_STYLE)
    system = SYSTEM_PROMPT.format(dj_style=style)
    result = await chat_json(hass, api_key, model, system, user_text)
    return _normalize(result, user_text)

def _normalize(data: dict, user_text: str) -> dict:
    data = dict(data or {})
    data.setdefault("intent", "play_music")
    data.setdefault("type", "search")
    data.setdefault("artist", None)
    data.setdefault("title", None)
    data.setdefault("playlist", None)
    data.setdefault("query", user_text)
    data.setdefault("spotify_search_query", user_text)
    data.setdefault("dj_announcement", "Daar gaan we. Ik zet hem voor je klaar.")
    if not data.get("spotify_search_query"):
        data["spotify_search_query"] = " ".join(str(x) for x in [data.get("artist"), data.get("title"), data.get("playlist")] if x)
    return data
