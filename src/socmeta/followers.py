"""Post → author → followers enrichment."""

from __future__ import annotations

import json
import re
from typing import Any

from curl_cffi import requests as crequests


def author_from_post(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize author identity from a socmeta post row."""
    platform = (row.get("platform") or "").lower()
    username = row.get("username") or row.get("channel") or row.get("uploader")
    display = row.get("display_name") or row.get("uploader") or row.get("channel")
    profile_url = row.get("profile_url")
    raw = row.get("raw") or {}

    if platform == "instagram" and username:
        handle = username
        if row.get("channel") and not str(row["channel"]).isdigit():
            handle = row["channel"]
        username = str(handle).lstrip("@")
        profile_url = f"https://www.instagram.com/{username}/"
    elif platform == "tiktok":
        from_url = None
        m = re.search(r"tiktok\.com/@([^/?#]+)", row.get("url") or "")
        if m:
            from_url = m.group(1)
        handle = from_url or row.get("uploader") or username
        username = str(handle).lstrip("@") if handle else None
        profile_url = f"https://www.tiktok.com/@{username}" if username else None
    elif platform == "x" and username:
        username = str(username).lstrip("@")
        profile_url = f"https://x.com/{username}"
    elif platform == "facebook":
        profile_url = (
            profile_url
            or raw.get("uploader_url")
            or (f"https://www.facebook.com/{username}" if username else None)
        )
    elif platform == "threads" and username:
        username = str(username).lstrip("@")
        profile_url = f"https://www.threads.com/@{username}"
    elif platform == "youtube":
        profile_url = profile_url or raw.get("uploader_url")

    return {
        "platform": platform,
        "username": username,
        "display_name": display,
        "profile_url": profile_url,
    }


def _tiktok_profile_followers(username: str) -> int | None:
    r = crequests.get(
        f"https://www.tiktok.com/@{username.lstrip('@')}",
        impersonate="chrome",
        timeout=30,
    )
    m = re.search(
        r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        r.text,
        re.S,
    )
    if not m:
        return None
    data = json.loads(m.group(1))
    info = (
        data.get("__DEFAULT_SCOPE__", {})
        .get("webapp.user-detail", {})
        .get("userInfo")
        or {}
    )
    stats = info.get("statsV2") or info.get("stats") or {}
    value = stats.get("followerCount")
    return int(value) if value is not None else None


def enrich_followers(row: dict[str, Any]) -> dict[str, Any]:
    """Fill ``followers`` using embedded post data or an author profile lookup."""
    out = dict(row)
    author = author_from_post(out)
    out["author"] = author
    out["author_profile"] = author.get("profile_url") or out.get("author_profile")

    if out.get("followers") is not None:
        out["followers_source"] = out.get("followers_source") or "post_embedded"
        return out

    platform = author.get("platform")
    followers = None
    source = None

    try:
        if platform == "instagram" and author.get("username"):
            from socmeta.platforms.instagram import profile_followers

            followers = profile_followers(author["username"])
            source = "instagram_profile"
        elif platform == "facebook" and author.get("profile_url"):
            from socmeta.platforms.facebook import profile_followers

            followers = profile_followers(author["profile_url"])
            source = "facebook_profile"
        elif platform == "threads" and author.get("username"):
            from socmeta.platforms.threads import profile_followers

            followers = profile_followers(author["username"])
            source = "threads_profile"
        elif platform == "tiktok" and author.get("username"):
            followers = _tiktok_profile_followers(author["username"])
            source = "tiktok_profile"
        elif platform in {"x", "youtube"}:
            source = "post_embedded_missing"
    except Exception as exc:  # noqa: BLE001
        out["followers_error"] = f"{type(exc).__name__}: {exc}"
        source = "error"

    out["followers"] = followers
    out["followers_source"] = source
    return out
