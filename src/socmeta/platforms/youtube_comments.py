"""YouTube comment extraction via yt-dlp ``getcomments``."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import yt_dlp

from socmeta.normalize import iso_from_timestamp
from socmeta.ytdlp_patch import apply as apply_ytdlp_patch


def video_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "youtu.be" in (parsed.netloc or ""):
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid or None
    qs = parse_qs(parsed.query or "")
    if qs.get("v"):
        return qs["v"][0]
    m = re.search(r"/(?:shorts|embed|live)/([A-Za-z0-9_-]{6,})", parsed.path or "")
    return m.group(1) if m else None


def _normalize(raw: dict[str, Any], *, parent_id: str | None = None) -> dict[str, Any]:
    author = (raw.get("author") or "").lstrip("@") or None
    row: dict[str, Any] = {
        "id": str(raw.get("id") or ""),
        "text": raw.get("text") or "",
        "likes": raw.get("like_count"),
        "created_at": iso_from_timestamp(raw.get("timestamp")),
        "username": author,
        "display_name": author,
        "user_id": str(raw.get("author_id")) if raw.get("author_id") is not None else None,
        "profile_url": raw.get("author_url"),
        "author_is_uploader": bool(raw.get("author_is_uploader")),
        "is_pinned": bool(raw.get("is_pinned")),
        "is_favorited": bool(raw.get("is_favorited")),
    }
    if parent_id:
        row["parent_id"] = parent_id
    return row


def list_youtube_comments(
    url: str,
    *,
    limit: int = 50,
    include_replies: bool = False,
    replies_limit: int = 20,
    sort: str = "newest",
) -> dict[str, Any]:
    """Fetch public comments for a YouTube video URL.

    Top-level only by default. ``sort`` selects yt-dlp ``comment_sort``
    (``new`` for newest, ``top`` for top/relevant); final ordering is applied
    by ``extract_comments``.
    """
    apply_ytdlp_patch()
    video_id = video_id_from_url(url) or ""
    sort_key = (sort or "newest").strip().lower()
    ytdlp_sort = "new" if sort_key in {"newest", "new", "recent", "latest"} else "top"

    # max_comments, max_parents, max_replies, max_replies_per_thread
    max_parents = max(int(limit), 1)
    if include_replies:
        max_replies = max(int(limit) * max(int(replies_limit), 1), 1)
        max_per_thread = max(int(replies_limit), 1)
        max_total = max_parents + max_replies
    else:
        max_replies = 0
        max_per_thread = 0
        max_total = max_parents

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": True,
        "ignore_no_formats_error": True,
        "extractor_args": {
            "youtube": {
                "max_comments": [
                    str(max_total),
                    str(max_parents),
                    str(max_replies),
                    str(max_per_thread),
                ],
                "comment_sort": [ytdlp_sort],
            }
        },
    }

    # Grab comment_count from metadata first — getcomments can overwrite it
    # with the fetched subset size when max_comments is set.
    meta_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": False,
        "ignore_no_formats_error": True,
    }
    with yt_dlp.YoutubeDL(meta_opts) as ydl:
        meta = ydl.extract_info(url, download=False) or {}
    total = meta.get("comment_count")

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError(f"No metadata returned for {url}")
    info.setdefault("title", meta.get("title"))
    info.setdefault("uploader", meta.get("uploader"))
    info.setdefault("channel", meta.get("channel"))

    raw_comments = info.get("comments") or []
    top_raw: list[dict[str, Any]] = []
    by_parent: dict[str, list[dict[str, Any]]] = {}

    for raw in raw_comments:
        parent = raw.get("parent") or "root"
        if parent == "root":
            top_raw.append(raw)
        else:
            by_parent.setdefault(str(parent), []).append(raw)

    # Keep API order for top/relevant so ranking is not discarded before limit.
    if ytdlp_sort == "new":
        top_raw.sort(key=lambda c: int(c.get("timestamp") or 0), reverse=True)
    top_raw = top_raw[:limit]

    comments: list[dict[str, Any]] = []
    replies_fetched = 0
    for raw in top_raw:
        row = _normalize(raw)
        cid = row["id"]
        if include_replies and cid:
            nested_raw = by_parent.get(cid, [])
            if ytdlp_sort == "new":
                nested_raw = sorted(
                    nested_raw,
                    key=lambda c: int(c.get("timestamp") or 0),
                    reverse=True,
                )
            nested_raw = nested_raw[:replies_limit]
            nested = [_normalize(n, parent_id=cid) for n in nested_raw]
            row["replies"] = nested
            row["reply_count"] = len(by_parent.get(cid, []))
            replies_fetched += len(nested)
        else:
            row["reply_count"] = len(by_parent.get(cid, [])) if cid else 0
        comments.append(row)

    note = (
        "Top-level comments via yt-dlp comment_sort=new."
        if ytdlp_sort == "new"
        else "Top-level comments via yt-dlp comment_sort=top."
    )
    if include_replies:
        note = f"Top-level + replies (up to {replies_limit} each). " + note

    return {
        "platform": "youtube",
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else url.split("?")[0],
        "id": video_id or info.get("id"),
        "title": info.get("title"),
        "username": info.get("uploader") or info.get("channel"),
        "comments": comments,
        "count": len(comments),
        "total": total if total is not None else info.get("comment_count"),
        "include_replies": include_replies,
        "replies_fetched": replies_fetched if include_replies else None,
        "source": "yt-dlp",
        "note": note,
        "status": "ok",
    }
