"""X / Twitter profile timeline via FixTweet (api.fxtwitter.com), no login."""

from __future__ import annotations

import time
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


def _is_reply(item: dict[str, Any]) -> bool:
    """True when the status is a reply (incl. self-thread continuations)."""
    replying_to = item.get("replying_to")
    if isinstance(replying_to, dict) and (replying_to.get("status") or replying_to.get("screen_name")):
        return True
    if item.get("replying_to_status") or item.get("in_reply_to_id") or item.get("in_reply_to_status_id"):
        return True
    if isinstance(replying_to, str) and replying_to.strip():
        return True
    return False


def _is_repost(item: dict[str, Any], handle: str) -> bool:
    """True when this timeline row is a retweet of someone else's post."""
    if item.get("reposted_by"):
        return True
    author = (item.get("author") or {}).get("screen_name")
    if author and str(author).lower() != handle.lower():
        return True
    return False


def list_profile_posts(
    username: str,
    *,
    limit: int = 20,
    include_replies: bool = False,
    include_reposts: bool = False,
) -> dict[str, Any]:
    """List recent posts from an X profile.

    By default skips replies (thread continuations) and retweets so the feed
    is the account's own standalone posts. Pass ``include_replies`` /
    ``include_reposts`` to keep them.
    """
    handle = username.lstrip("@")
    posts: list[dict[str, Any]] = []
    cursor: str | None = None
    author_meta: dict[str, Any] = {}
    pages = 0

    while len(posts) < limit and pages < 15:
        pages += 1
        url = f"https://api.fxtwitter.com/2/profile/{quote(handle)}/statuses"
        if cursor:
            url += f"?cursor={quote(cursor)}"
        resp = None
        for attempt in range(3):
            resp = crequests.get(url, impersonate="chrome", timeout=30)
            # FixTweet occasionally 404s transiently even for valid public profiles.
            if resp.status_code == 200:
                break
            if resp.status_code in {404, 429, 502, 503} and attempt < 2:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise RuntimeError(
                f"X profile feed HTTP {resp.status_code}: {resp.text[:200]}"
            )
        assert resp is not None
        data = resp.json() or {}
        results = data.get("results") or []
        if not results:
            break
        for item in results:
            if item.get("type") and item.get("type") != "status":
                continue
            if not include_replies and _is_reply(item):
                continue
            if not include_reposts and _is_repost(item, handle):
                continue
            author = item.get("author") or {}
            # Prefer profile handle meta over a retweet's original author.
            if not author_meta:
                rb = item.get("reposted_by") if isinstance(item.get("reposted_by"), dict) else None
                src = rb or author
                author_meta = {
                    "username": (src.get("screen_name") if src else None) or handle,
                    "display_name": (src.get("name") if src else None) or author.get("name"),
                    "followers": author.get("followers") if not rb else None,
                    "profile_url": f"https://x.com/{handle}",
                }
            # Fill followers from a later own-post author object if missing
            if author_meta.get("followers") is None and author.get("screen_name", "").lower() == handle.lower():
                author_meta["followers"] = author.get("followers")
                author_meta["display_name"] = author.get("name") or author_meta.get("display_name")
            tid = str(item.get("id") or "")
            replying_to = item.get("replying_to") if isinstance(item.get("replying_to"), dict) else None
            is_rt = bool(item.get("reposted_by"))
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
                "is_reply": bool(replying_to),
                "is_repost": is_rt,
                "reply_to_id": (replying_to or {}).get("status"),
                "status": "ok",
            })
            if len(posts) >= limit:
                break
        bottom = ((data.get("cursor") or {}).get("bottom") if isinstance(data.get("cursor"), dict) else None)
        if not bottom or bottom == cursor:
            break
        cursor = bottom

    notes = []
    if not include_replies:
        notes.append("replies excluded")
    if not include_reposts:
        notes.append("reposts excluded")

    # Profile card via dedicated endpoint when followers still missing
    if author_meta.get("followers") is None:
        try:
            pr = crequests.get(
                f"https://api.fxtwitter.com/{quote(handle)}",
                impersonate="chrome",
                timeout=20,
            )
            if pr.status_code == 200:
                user = (pr.json() or {}).get("user") or {}
                author_meta["followers"] = user.get("followers")
                author_meta["display_name"] = user.get("name") or author_meta.get("display_name")
                author_meta["username"] = user.get("screen_name") or author_meta.get("username")
        except Exception:  # noqa: BLE001
            pass

    return {
        "platform": "x",
        "username": author_meta.get("username") or handle,
        "display_name": author_meta.get("display_name"),
        "followers": author_meta.get("followers"),
        "profile_url": author_meta.get("profile_url") or f"https://x.com/{handle}",
        "posts": posts[:limit],
        "count": min(len(posts), limit),
        "source": "fxtwitter",
        "note": (", ".join(notes) + " by default.") if notes else None,
    }
