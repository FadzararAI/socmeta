"""Threads post/profile adapter.

Uses the vendored ``threads_scraper`` module (MIT, ToolzerHub).
See ``socmeta/vendor/THREADS_LICENSE``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from socmeta.vendor.threads_scraper import Threads


def resolve_share_url(url: str) -> str:
    if "/post/" in url:
        return url.split("?")[0]
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as resp:
        return resp.geturl().split("?")[0]


def extract_threads(url: str) -> dict[str, Any]:
    resolved = resolve_share_url(url)
    # Share links resolve to /@user/post/CODE
    path = urlparse(resolved).path
    if "/post/" not in path:
        raise ValueError(f"Could not resolve Threads post URL: {url} → {resolved}")

    scraper = Threads()
    post = scraper.post(resolved)
    username = post.get("username")
    followers = None
    if username:
        try:
            prof = scraper.profile(username)
            followers = prof.get("followers_count")
        except Exception:  # noqa: BLE001
            followers = None

    return {
        "platform": "threads",
        "url": url,
        "resolved_url": resolved,
        "id": post.get("id") or post.get("code"),
        "username": username,
        "display_name": post.get("full_name"),
        "profile_url": f"https://www.threads.com/@{username}" if username else None,
        "caption": post.get("text"),
        "likes": post.get("like_count"),
        "comments": post.get("reply_count"),
        "reposts": post.get("repost_count"),
        "shares": post.get("share_count"),
        "bookmarks": None,
        "quotes": post.get("quote_count"),
        "views": post.get("view_count"),
        "followers": followers,
        "followers_source": "threads_profile" if followers is not None else None,
        "post_date": post.get("created_at"),
        "raw": {"code": post.get("code")},
    }


def profile_followers(username: str) -> int | None:
    prof = Threads().profile(username.lstrip("@"))
    return prof.get("followers_count")
