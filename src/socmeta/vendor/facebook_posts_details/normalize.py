"""Coercing Facebook's display values into stable Python types."""

from __future__ import annotations

import re
from datetime import datetime, timezone

__all__ = []

_COUNT_RE = re.compile(r"([\d.,]+)\s*([KMB])?", re.IGNORECASE)


_COUNT_MULTIPLIER = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


#: Facebook's stand-in alt-text when an image has no real description.
_PLACEHOLDER_CAPTIONS = frozenset({
    "No photo description available.",
    "No description available.",
    "May be an image.",
})


def _to_int(value):
    """Coerce a count to ``int``; ``None`` when it is not a number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return _parse_count(value)
    return None


def _parse_count(text):
    """``'1.4M followers'`` -> ``1400000``; ``'41 following'`` -> ``41``."""
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return int(text)
    if not isinstance(text, str):
        return None

    match = _COUNT_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        number = float(match.group(1).rstrip("."))
    except ValueError:
        return None
    suffix = (match.group(2) or "").upper()
    return int(number * _COUNT_MULTIPLIER[suffix])


def _to_iso(timestamp):
    """Unix seconds -> ISO-8601 UTC string."""
    timestamp = _to_int(timestamp)
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _image(url, caption=None):
    """A post image. Placeholder alt-text is normalised away to ``None``."""
    if caption is not None:
        caption = caption.strip()
        if not caption or caption in _PLACEHOLDER_CAPTIONS:
            caption = None
    return {"url": url, "caption": caption}


def _about_entry(value, url=None):
    return {"value": value, "url": url}


def _add_about(bucket, key, entry):
    """Append ``entry`` under ``key`` -- values are always lists, never scalars."""
    bucket.setdefault(key, []).append(entry)
