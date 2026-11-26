"""Pulling ids and content types out of Facebook URLs."""

from __future__ import annotations

import re
import urllib.parse as up

__all__ = ["get_profile_id_from_url", "get_post_id_from_url", "get_post_type_from_url"]

_PEOPLE_ID_RE = re.compile(r"/(?:people|pages)/[^/]+/(\d+)")


_EVENT_ID_RE = re.compile(r"/events/(\d+)")


_POST_ID_MARKERS = ("reel", "reels", "videos", "video", "posts", "photos", "watch")


def get_profile_id_from_url(url):
    """Extract the username or numeric profile id from a Facebook URL."""
    if not url:
        return ""
    clean_url = url.split("?")[0].rstrip("/")
    parsed = up.urlparse(url)

    if "profile.php" in clean_url:
        queries = up.parse_qs(parsed.query)
        if "id" in queries:
            return queries["id"][0]

    match = _PEOPLE_ID_RE.search(clean_url)
    if match:
        return match.group(1)

    match = _EVENT_ID_RE.search(clean_url)
    if match:
        return match.group(1)

    parts = parsed.path.strip("/").split("/")
    return parts[-1] if parts else ""


def get_post_id_from_url(url):
    """Extract the post / reel / video id from a Facebook URL."""
    if not url:
        return None
    parsed = up.urlparse(url)

    queries = up.parse_qs(parsed.query)
    for key in ("story_fbid", "fbid", "v"):
        if key in queries and queries[key]:
            return queries[key][0]

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not parts:
        return None

    # Prefer whatever follows a /reel/, /posts/, /videos/ ... marker, and within
    # that prefer the numeric id (video URLs put a slugged title in between).
    for marker in _POST_ID_MARKERS:
        if marker not in parts:
            continue
        tail = parts[parts.index(marker) + 1:]
        if not tail:
            continue
        for segment in reversed(tail):
            if segment.isdigit():
                return segment
        return up.unquote(tail[0])

    digits = [p for p in parts if p.isdigit()]
    if digits:
        return digits[-1]
    return up.unquote(parts[-1])


def get_post_type_from_url(url):
    """Classify a URL as ``reel`` / ``video`` / ``photo`` / ``story`` / ``post``."""
    if not url:
        return None
    path = up.urlparse(url).path.lower()
    parts = set(path.strip("/").split("/"))

    if parts & {"reel", "reels"}:
        return "reel"
    if parts & {"videos", "video", "watch"}:
        return "video"
    if parts & {"photo", "photos"}:
        return "photo"
    if "story.php" in path or "stories" in parts:
        return "story"
    return "post"


def _guess_kind(url):
    """``post`` for anything that looks like a piece of content, else ``profile``."""
    path = up.urlparse(url).path.lower()
    parts = set(path.strip("/").split("/"))
    if parts & {"reel", "reels", "videos", "video", "watch", "photo", "photos",
                "posts", "permalink", "stories"}:
        return "post"
    if "story.php" in path or "permalink.php" in path:
        return "post"
    return "profile"
