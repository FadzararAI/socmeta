"""X / Twitter comment (reply) extraction via FixTweet conversation API."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import quote, urlparse

from curl_cffi import requests as crequests

from socmeta.normalize import iso_from_timestamp

RankingMode = Literal["likes", "recency"]


def status_id_from_url(url: str) -> str | None:
    m = re.search(r"/status/(\d+)", urlparse(url).path or url)
    return m.group(1) if m else None


def _created_iso(item: dict[str, Any]) -> str | None:
    ts = item.get("created_timestamp")
    if ts is not None:
        return iso_from_timestamp(ts)
    return item.get("created_at")


def _parent_status_id(item: dict[str, Any]) -> str | None:
    replying_to = item.get("replying_to")
    if isinstance(replying_to, dict) and replying_to.get("status"):
        return str(replying_to["status"])
    for key in ("replying_to_status", "in_reply_to_status_id", "in_reply_to_id"):
        val = item.get(key)
        if isinstance(val, list) and val:
            return str(val[0])
        if val:
            return str(val)
    return None


def _normalize(item: dict[str, Any], *, parent_id: str | None = None) -> dict[str, Any]:
    author = item.get("author") or {}
    username = author.get("screen_name") or author.get("username")
    row: dict[str, Any] = {
        "id": str(item.get("id") or ""),
        "text": item.get("text") or "",
        "likes": item.get("likes"),
        "reposts": item.get("reposts") or item.get("retweets"),
        "comments": item.get("replies"),
        "views": item.get("views"),
        "bookmarks": item.get("bookmarks"),
        "created_at": _created_iso(item),
        "username": username,
        "display_name": author.get("name") or username,
        "user_id": str(author.get("id")) if author.get("id") is not None else None,
        "profile_url": (
            author.get("url")
            or (f"https://x.com/{username}" if username else None)
        ),
        "url": item.get("url") or (f"https://x.com/{username}/status/{item.get('id')}" if username and item.get("id") else None),
        "reply_count": item.get("replies") or 0,
    }
    pid = parent_id or _parent_status_id(item)
    if pid:
        row["parent_id"] = pid
    return row


def _fetch_conversation_page(
    status_id: str,
    *,
    ranking_mode: RankingMode,
    cursor: str | None,
) -> dict[str, Any]:
    url = f"https://api.fxtwitter.com/2/conversation/{quote(status_id)}?ranking_mode={ranking_mode}"
    if cursor:
        url += f"&cursor={quote(cursor)}"
    last_err = None
    for attempt in range(3):
        resp = crequests.get(url, impersonate="chrome", timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in {404, 429, 502, 503} and attempt < 2:
            last_err = resp.status_code
            continue
        raise RuntimeError(f"X conversation HTTP {resp.status_code}: {resp.text[:200]}")
    raise RuntimeError(f"X conversation failed after retries (last={last_err})")


def list_x_comments(
    url: str,
    *,
    limit: int = 50,
    include_replies: bool = False,
    replies_limit: int = 20,
    ranking_mode: RankingMode = "recency",
) -> dict[str, Any]:
    """Fetch public replies for an X status URL.

    By default returns only top-level replies to the post (``include_replies``
    False). When True, nests replies-to-replies under their parents when they
    appear in the conversation pages (capped by ``replies_limit``).

    ``ranking_mode``: ``recency`` (newest first, default) or ``likes``.
    """
    status_id = status_id_from_url(url)
    if not status_id:
        raise ValueError(f"Could not parse X status id from URL: {url}")

    root: dict[str, Any] | None = None
    all_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor: str | None = None
    pages = 0
    total = None

    while pages < 20:
        pages += 1
        data = _fetch_conversation_page(status_id, ranking_mode=ranking_mode, cursor=cursor)
        if root is None:
            root = data.get("status") if isinstance(data.get("status"), dict) else None
            if root:
                total = root.get("replies")
        for item in data.get("replies") or []:
            if not isinstance(item, dict):
                continue
            iid = str(item.get("id") or "")
            if not iid or iid in seen:
                continue
            seen.add(iid)
            all_items.append(item)

        # Enough top-level collected?
        top_n = sum(1 for it in all_items if _parent_status_id(it) == status_id)
        bottom = ((data.get("cursor") or {}) if isinstance(data.get("cursor"), dict) else {}).get("bottom")
        if top_n >= limit or not bottom or bottom == cursor:
            break
        cursor = bottom

    # Split into top-level vs nested
    top_items = [it for it in all_items if _parent_status_id(it) == status_id][:limit]
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for it in all_items:
        pid = _parent_status_id(it)
        if not pid or pid == status_id:
            continue
        by_parent.setdefault(pid, []).append(it)

    comments: list[dict[str, Any]] = []
    replies_fetched = 0
    for it in top_items:
        row = _normalize(it, parent_id=status_id)
        if include_replies:
            nested_raw = by_parent.get(str(it.get("id")), [])[:replies_limit]
            nested = [_normalize(n, parent_id=str(it.get("id"))) for n in nested_raw]
            row["replies"] = nested
            replies_fetched += len(nested)
        comments.append(row)

    note = {
        "likes": "Top-level replies fetched by likes ranking.",
        "recency": "Top-level replies fetched by recency ranking.",
    }.get(ranking_mode, "Top-level replies.")
    if not include_replies:
        note += " Nested replies excluded (pass --include-replies)."
    else:
        note += f" Nested replies included (up to {replies_limit} per comment)."

    return {
        "platform": "x",
        "url": (root or {}).get("url") or url.split("?")[0],
        "id": status_id,
        "username": ((root or {}).get("author") or {}).get("screen_name"),
        "comments": comments,
        "count": len(comments),
        "total": total,
        "include_replies": include_replies,
        "replies_fetched": replies_fetched if include_replies else None,
        "ranking_mode": ranking_mode,
        "source": "fxtwitter-conversation",
        "note": note,
        "status": "ok",
    }
