from __future__ import annotations

from typing import Any


def entry_unique_id(runtime: Any, suffix: str) -> str:
    """Return a unique entity id suffix scoped to the config entry."""
    entry_id = str(getattr(getattr(runtime, "entry", None), "entry_id", "") or "default")
    clean_suffix = str(suffix or "").removeprefix("djconnect_")
    return f"djconnect_{entry_id}_{clean_suffix}"
