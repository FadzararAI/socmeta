from __future__ import annotations

from typing import Any

import yt_dlp

from socmeta.normalize import normalize_ytdlp, iso_from_timestamp, _as_int
from socmeta.ytdlp_patch import apply as apply_ytdlp_patch


def extract_via_ytdlp(
    url: str,
    *,
    platform: str,
    cookies_from_browser: str | None = None,
    cookiefile: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    apply_ytdlp_patch()

    opts: dict[str, Any] = {
        "quiet": not verbose,
        "no_warnings": not verbose,
        "skip_download": True,
        "ignoreerrors": False,
        "extract_flat": False,
        "ignore_no_formats_error": True,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if cookiefile:
        opts["cookiefile"] = cookiefile

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise RuntimeError(f"No metadata returned for {url}")
        if info.get("_type") == "playlist" and info.get("entries"):
            entries = [e for e in info["entries"] if e]
            if len(entries) == 1:
                info = entries[0]
        return normalize_ytdlp(info, url=url, platform=platform)


def list_via_ytdlp(
    profile_url: str,
    *,
    platform: str,
    username: str,
    limit: int = 20,
    cookies_from_browser: str | None = None,
    cookiefile: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """List recent posts/videos from a profile URL using yt-dlp flat playlist mode."""
    apply_ytdlp_patch()

    opts: dict[str, Any] = {
        "quiet": not verbose,
        "no_warnings": not verbose,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": limit,
        "ignoreerrors": True,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if cookiefile:
        opts["cookiefile"] = cookiefile

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(profile_url, download=False)
    if not info:
        raise RuntimeError(f"No playlist data for {profile_url}")

    entries = [e for e in (info.get("entries") or []) if e][:limit]
    posts: list[dict[str, Any]] = []
    for e in entries:
        post_url = e.get("url") or e.get("webpage_url")
        if post_url and not str(post_url).startswith("http"):
            # TikTok sometimes returns bare ids
            if platform == "tiktok":
                post_url = f"https://www.tiktok.com/@{username}/video/{e.get('id')}"
            elif platform == "youtube":
                post_url = f"https://www.youtube.com/watch?v={e.get('id')}"
        posts.append({
            "platform": platform,
            "url": post_url,
            "id": e.get("id") or e.get("display_id"),
            "username": e.get("uploader") or e.get("channel") or username,
            "display_name": e.get("uploader") or e.get("channel") or info.get("uploader") or info.get("channel"),
            "caption": e.get("description") or e.get("title"),
            "likes": _as_int(e.get("like_count")),
            "comments": _as_int(e.get("comment_count")),
            "reposts": None if platform == "tiktok" else _as_int(e.get("repost_count")),
            "shares": _as_int(e.get("repost_count") if platform == "tiktok" else e.get("share_count")),
            "bookmarks": _as_int(e.get("bookmark_count") or e.get("save_count")),
            "views": _as_int(e.get("view_count")),
            "post_date": iso_from_timestamp(e.get("timestamp")) or e.get("upload_date"),
            "duration": e.get("duration"),
            "status": "ok",
        })

    return {
        "platform": platform,
        "username": username,
        "display_name": info.get("uploader") or info.get("channel") or info.get("title"),
        "followers": _as_int(info.get("channel_follower_count")),
        "profile_url": profile_url,
        "posts": posts,
        "count": len(posts),
        "source": "yt-dlp",
    }
