"""Threads comment + optional nested-reply extraction from the permalink page."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from socmeta.vendor.threads_scraper import Threads, clean_post, post_path_of, walk


def _normalize(raw: dict[str, Any], *, parent_id: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": raw.get("id") or raw.get("code"),
        "text": raw.get("text") or "",
        "likes": raw.get("like_count"),
        "created_at": raw.get("created_at"),
        "username": raw.get("username"),
        "display_name": raw.get("full_name"),
        "profile_url": (
            f"https://www.threads.com/@{raw['username']}" if raw.get("username") else None
        ),
        "reply_count": raw.get("reply_count") or 0,
        "url": raw.get("url"),
        "reply_to_username": raw.get("reply_to_username"),
    }
    if parent_id:
        row["parent_id"] = parent_id
    return row


def _direct_reply_edges(blobs: Any, post: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    host = next(
        (
            n
            for n in walk(blobs)
            if n.get("id") == post.get("id")
            and (n.get("text_post_app_info") or {}).get("direct_replies")
        ),
        None,
    )
    replies = (((host or {}).get("text_post_app_info") or {}).get("direct_replies") or {})
    edges = replies.get("edges") or []
    page_info = replies.get("page_info") or {}
    return edges, page_info


def list_threads_comments(
    url: str,
    *,
    limit: int = 50,
    include_replies: bool = False,
    replies_limit: int = 20,
) -> dict[str, Any]:
    """Fetch public comments (direct replies) for a Threads post URL.

    Top-level comments only by default. With ``include_replies=True``, nested
    replies under each top-level comment are included (capped by
    ``replies_limit``).
    """
    path = post_path_of(url.split("?")[0])
    code = path.rsplit("/", 1)[1]
    scraper = Threads()
    blobs = scraper.page(path)
    post = next(
        (n for n in walk(blobs) if n.get("code") == code and n.get("user") and n.get("taken_at")),
        None,
    )
    if post is None:
        raise RuntimeError(f"Threads post not found or not public: {url}")

    root = clean_post(post)
    edges, page_info = _direct_reply_edges(blobs, post)

    comments: list[dict[str, Any]] = []
    replies_fetched = 0

    for edge in edges:
        if len(comments) >= limit:
            break
        node = (edge or {}).get("node") or {}
        post_edges = ((node.get("posts") or {}).get("edges") or [])
        cleaned = [clean_post(pe["node"]) for pe in post_edges if pe.get("node")]
        if not cleaned:
            continue
        top = _normalize(cleaned[0])
        if include_replies and len(cleaned) > 1:
            nested = [
                _normalize(r, parent_id=top["id"])
                for r in cleaned[1 : 1 + replies_limit]
            ]
            top["replies"] = nested
            replies_fetched += len(nested)
        comments.append(top)

    total = root.get("reply_count")
    note = "Top-level comments only." if not include_replies else (
        f"Top-level comments + nested replies (up to {replies_limit} per thread)."
    )
    if page_info.get("has_next_page") and (total is None or len(comments) < (total or 0)):
        note += " More replies may exist beyond the first permalink page."

    return {
        "platform": "threads",
        "url": url.split("?")[0],
        "id": root.get("id") or root.get("code"),
        "username": root.get("username"),
        "comments": comments,
        "count": len(comments),
        "total": total,
        "include_replies": include_replies,
        "replies_fetched": replies_fetched if include_replies else None,
        "source": "threads-permalink",
        "note": note,
        "status": "ok",
    }
