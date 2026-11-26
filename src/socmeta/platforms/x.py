"""X / Twitter profile timeline via FixTweet (api.fxtwitter.com), no login."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from curl_cffi import requests as crequests

from socmeta.normalize import iso_from_timestamp


def _created_iso(item: dict[str, Any]) -> str | None:
    ts = item.get("created_timestamp")
    if ts is not None:
        return iso_from_timestamp(ts)
    raw = item.get("created_at")
    if not raw:
        return None
    try:
        # e.g. Thu Nov 26 10:33:01 +0000 2026
        dt = datetime.strptime(str(raw), "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return str(raw)


def list_profile_posts(username: str, *, limit: int = 20) -> dict[str, Any]:
    handle = username.lstrip("@")
    posts: list[dict[str, Any]] = []
    cursor: str | None = None
    author_meta: dict[str, Any] = {}

    while len(posts) < limit:
        url = f"https://api.fxtwitter.com/2/profile/{quote(handle)}/statuses"
        if cursor:
            url += f"?cursor={quote(cursor)}"
        resp = crequests.get(url, impersonate="chrome", timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"X profile feed HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json() or {}
        results = data.get("results") or []
        if not results:
            break
        for item in results:
            if item.get("type") and item.get("type") != "status":
                continue
            author = item.get("author") or {}
            if not author_meta and author:
                author_meta = {
                    "username": author.get("screen_name") or handle,
                    "display_name": author.get("name"),
                    "followers": author.get("followers"),
                    "profile_url": author.get("url") or f"https://x.com/{handle}",
                }
            tid = str(item.get("id") or "")
            posts.append({
                "platform": "x",
                "url": item.get("url") or (f"https://x.com/{handle}/status/{tid}" if tid else None),
                "id": tid or None,
                "username": (author.get("screen_name") or handle),
                "display_name": author.get("name"),
                "caption": item.get("text") or ((item.get("raw_text") or {}).get("text")),
                "likes": item.get("likes"),
                "comments": item.get("replies"),
                "reposts": item.get("reposts"),
                "shares": None,
                "bookmarks": item.get("bookmarks"),
                "views": item.get("views"),
                "quotes": item.get("quotes"),
                "post_date": _created_iso(item),
                "status": "ok",
            })
            if len(posts) >= limit:
                break
        bottom = ((data.get("cursor") or {}).get("bottom") if isinstance(data.get("cursor"), dict) else None)
        if not bottom or bottom == cursor:
            break
        cursor = bottom

    return {
        "platform": "x",
        "username": author_meta.get("username") or handle,
        "display_name": author_meta.get("display_name"),
        "followers": author_meta.get("followers"),
        "profile_url": author_meta.get("profile_url") or f"https://x.com/{handle}",
        "posts": posts[:limit],
        "count": min(len(posts), limit),
        "source": "fxtwitter",
    }
