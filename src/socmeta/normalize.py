from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .detect import detect_platform


def iso_from_timestamp(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_ytdlp(info: dict[str, Any], *, url: str, platform: str | None = None) -> dict[str, Any]:
    """Map a yt-dlp info dict into the shared socmeta schema."""
    platform = platform or detect_platform(url) or str(info.get("extractor_key", "unknown")).lower()
    username = info.get("uploader_id") or info.get("channel_id") or info.get("uploader")
    display_name = info.get("uploader") or info.get("channel")
    handle = info.get("channel") or info.get("uploader") or username

    repost_count = info.get("repost_count")
    share_count = info.get("share_count")

    # yt-dlp often folds platform-specific share/repost metrics into repost_count.
    if platform in {"tiktok", "facebook"}:
        shares = share_count if share_count is not None else repost_count
        reposts = None
    else:
        shares = share_count
        reposts = repost_count

    bookmarks = info.get("bookmark_count")
    if bookmarks is None:
        bookmarks = info.get("save_count")

    return {
        "platform": platform,
        "url": url,
        "id": info.get("id") or info.get("display_id"),
        "username": handle,
        "display_name": display_name,
        "caption": info.get("description") or info.get("title"),
        "likes": info.get("like_count"),
        "comments": info.get("comment_count"),
        "reposts": reposts,
        "shares": shares,
        "bookmarks": bookmarks,
        "views": info.get("view_count"),
        "followers": _as_int(info.get("channel_follower_count")),
        "channel": info.get("channel"),
        "uploader": info.get("uploader"),
        "post_date": iso_from_timestamp(info.get("timestamp")) or info.get("upload_date"),
        "raw": {
            "extractor": info.get("extractor"),
            "extractor_key": info.get("extractor_key"),
            "title": info.get("title"),
            "uploader_url": info.get("uploader_url") or info.get("channel_url"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
        },
    }
