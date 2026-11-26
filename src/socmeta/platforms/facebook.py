"""Facebook post/profile adapter.

Uses the vendored ``facebook_posts_details`` library (MIT, Aman / binarykernal).
See ``socmeta/vendor/facebook_posts_details/LICENSE``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from socmeta.normalize import iso_from_timestamp
from socmeta.vendor import facebook_posts_details as fb
from socmeta.vendor.facebook_posts_details.http import fetch_html


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
    cleaned = str(text).lower().replace(",", "")
    m = re.search(r"([\d.]+)\s*([kmb])?", cleaned)
    if not m:
        return None
    num = float(m.group(1))
    mult = {None: 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[m.group(2)]
    return int(num * mult)


def _base_profile(url: str) -> str:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    # strip trailing tab segments
    while parts and parts[-1].lower() in {"reels", "videos", "posts", "photos", "about", "reviews"}:
        parts.pop()
    path = "/" + "/".join(parts) if parts else ""
    return f"https://www.facebook.com{path}"


def list_profile_posts(profile_url: str, *, limit: int = 20) -> dict[str, Any]:
    """List recent public reel/video/post IDs from a Facebook page.

    Logged-out Facebook pages expose a limited set of media IDs (best on the
    Reels tab). Full engagement metrics require enrich=True (per-post scrape).
    """
    base = _base_profile(profile_url)
    tabs = [base, f"{base}/reels", f"{base}/videos"]

    video_ids: list[str] = []
    post_ids: list[str] = []
    display_name = None
    followers = None

    for tab in tabs:
        try:
            html = fetch_html(tab) or ""
        except Exception:  # noqa: BLE001
            continue
        if not display_name:
            m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html, re.I)
            if m:
                display_name = m.group(1).split(" | ")[0].strip() or m.group(1)
        for vid in re.findall(r'"video_id"\s*:\s*"?(\d+)"?', html):
            if vid not in video_ids:
                video_ids.append(vid)
        for pid in re.findall(r'"post_id"\s*:\s*"?(\d+)"?', html):
            if pid not in post_ids:
                post_ids.append(pid)
        if len(video_ids) + len(post_ids) >= limit * 2:
            break

    try:
        followers = profile_followers(base)
    except Exception:  # noqa: BLE001
        followers = None

    posts: list[dict[str, Any]] = []
    for vid in video_ids:
        posts.append({
            "platform": "facebook",
            "url": f"https://www.facebook.com/reel/{vid}",
            "id": vid,
            "username": display_name,
            "display_name": display_name,
            "caption": None,
            "likes": None,
            "comments": None,
            "reposts": None,
            "shares": None,
            "bookmarks": None,
            "views": None,
            "post_date": None,
            "status": "ok",
            "kind": "reel",
        })
        if len(posts) >= limit:
            break

    if len(posts) < limit:
        for pid in post_ids:
            # Avoid duplicating ids already used as reels
            if pid in video_ids:
                continue
            # Prefer page-scoped post URL when username slug is available
            slug = [p for p in urlparse(base).path.split("/") if p]
            if slug and not slug[0].isdigit() and slug[0] != "profile.php":
                post_url = f"https://www.facebook.com/{slug[0]}/posts/{pid}"
            else:
                post_url = f"https://www.facebook.com/{pid}"
            posts.append({
                "platform": "facebook",
                "url": post_url,
                "id": pid,
                "username": display_name,
                "display_name": display_name,
                "caption": None,
                "likes": None,
                "comments": None,
                "reposts": None,
                "shares": None,
                "bookmarks": None,
                "views": None,
                "post_date": None,
                "status": "ok",
                "kind": "post",
            })
            if len(posts) >= limit:
                break

    return {
        "platform": "facebook",
        "username": display_name or ([p for p in urlparse(base).path.split("/") if p] or [None])[0],
        "display_name": display_name,
        "followers": followers,
        "profile_url": base,
        "posts": posts[:limit],
        "count": min(len(posts), limit),
        "source": "facebook_page_tabs",
        "note": "Logged-out FB feeds are sparse; Reels tab works best. Use enrich=True for metrics.",
    }
