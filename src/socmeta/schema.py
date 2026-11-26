"""Shared post metadata schema + field coverage notes."""

from __future__ import annotations

from typing import Any

# What each platform typically exposes for a public media post.
FIELD_COVERAGE: dict[str, dict[str, bool | str]] = {
    "youtube": {
        "likes": True,
        "comments": True,
        "shares": False,
        "reposts": False,
        "bookmarks": False,
        "views": True,
        "followers": True,
        "post_date": True,
    },
    "facebook": {
        "likes": True,
        "comments": True,
        "shares": True,
        "reposts": False,
        "bookmarks": False,
        "views": True,
        "followers": True,  # via author profile
        "post_date": True,
    },
    "tiktok": {
        "likes": True,
        "comments": True,
        "shares": True,
        "reposts": False,
        "bookmarks": True,  # saves
        "views": True,
        "followers": True,  # embedded on post
        "post_date": True,
    },
    "x": {
        "likes": True,
        "comments": True,
        "shares": False,
        "reposts": True,
        "bookmarks": True,
        "views": True,
        "followers": True,  # embedded on post
        "post_date": True,
    },
    "instagram": {
        "likes": True,
        "comments": True,
        "shares": False,
        "reposts": False,
        "bookmarks": False,
        "views": "partial",
        "followers": True,  # via author profile
        "post_date": True,
    },
    "threads": {
        "likes": True,
        "comments": True,
        "shares": True,
        "reposts": True,
        "bookmarks": False,
        "views": True,
        "followers": True,  # via author profile
        "post_date": True,
    },
}

PUBLIC_KEYS = (
    "platform",
    "url",
    "id",
    "username",
    "display_name",
    "author_profile",
    "caption",
    "likes",
    "comments",
    "reposts",
    "shares",
    "bookmarks",
    "views",
    "followers",
    "followers_source",
    "post_date",
    "status",
)


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    """Strip internal keys for CLI / JSON output."""
    out = {k: row.get(k) for k in PUBLIC_KEYS if k in row or k in (
        "platform", "url", "likes", "comments", "reposts", "shares",
        "bookmarks", "views", "followers", "username", "caption", "post_date",
    )}
    if row.get("error"):
        out["error"] = row["error"]
        out["status"] = row.get("status") or "fail"
    else:
        out.setdefault("status", "ok")
    return out
