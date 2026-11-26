"""Facebook post/profile adapter.

Uses the vendored ``facebook_posts_details`` library (MIT, Aman / binarykernal).
See ``socmeta/vendor/facebook_posts_details/LICENSE``.
"""

from __future__ import annotations

from typing import Any

from socmeta.normalize import iso_from_timestamp
from socmeta.vendor import facebook_posts_details as fb


def extract_facebook(url: str, *, with_profile: bool = True) -> dict[str, Any]:
    data = fb.post_data(url, with_profile=with_profile)
    if not data:
        raise RuntimeError(f"Facebook returned no data for {url}")

    user = data.get("user") or {}
    followers = user.get("followers") or data.get("followers")
    profile_url = data.get("profile_url")

    return {
        "platform": "facebook",
        "url": url,
        "id": data.get("post_id"),
        "username": data.get("name"),
        "display_name": data.get("name"),
        "profile_url": profile_url,
        "caption": data.get("post_text"),
        "likes": data.get("likes_count"),
        "comments": data.get("comments_count"),
        "reposts": None,
        "shares": data.get("share_count"),
        "bookmarks": None,
        "views": data.get("views_count"),
        "followers": followers,
        "followers_source": "facebook_post_profile" if followers is not None else None,
        "post_date": data.get("publish_date_iso") or iso_from_timestamp(data.get("publish_date")),
        "raw": {"uploader_url": profile_url, "post_type": data.get("post_type")},
    }


def profile_followers(profile_url: str) -> int | None:
    data = fb.profile_data(profile_url)
    if not data:
        return None
    value = data.get("followers")
    if value is not None:
        return int(value)
    text = data.get("followers_text")
    if not text:
        return None
    import re

    cleaned = str(text).lower().replace(",", "")
    m = re.search(r"([\d.]+)\s*([kmb])?", cleaned)
    if not m:
        return None
    num = float(m.group(1))
    mult = {None: 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[m.group(2)]
    return int(num * mult)
