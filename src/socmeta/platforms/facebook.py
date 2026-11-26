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


def _profile_id_from_url(url: str) -> str | None:
    m = re.search(r"[?&]id=(\d+)", url)
    if m:
        return m.group(1)
    parts = [p for p in urlparse(url).path.split("/") if p]
    # /people/Name/6159... or bare numeric
    for p in reversed(parts):
        if p.isdigit() and len(p) >= 10:
            return p
    return None


def _base_profile(url: str) -> str:
    """Normalize a Facebook profile/page URL, keeping profile.php?id=."""
    parsed = urlparse(url)
    profile_id = _profile_id_from_url(url)
    if "profile.php" in (parsed.path or "") and profile_id:
        return f"https://www.facebook.com/profile.php?id={profile_id}"
    if profile_id and (not parsed.path or parsed.path in {"/", ""}):
        return f"https://www.facebook.com/profile.php?id={profile_id}"

    parts = [p for p in parsed.path.split("/") if p]
    while parts and parts[-1].lower() in {"reels", "videos", "posts", "photos", "about", "reviews"}:
        parts.pop()
    if parts and parts[0] == "people" and profile_id:
        return f"https://www.facebook.com/profile.php?id={profile_id}"
    path = "/" + "/".join(parts) if parts else ""
    return f"https://www.facebook.com{path}"


def _profile_tabs(base: str) -> list[str]:
    """Candidate feed URLs for a page/profile (logged-out)."""
    if "profile.php" in base and "id=" in base:
        return [
            base,
            f"{base}&sk=reels_tab" if "?" in base else f"{base}?sk=reels_tab",
        ]
    return [base, f"{base.rstrip('/')}/reels", f"{base.rstrip('/')}/videos"]


def _post_url_for(base: str, post_id: str) -> str:
    profile_id = _profile_id_from_url(base)
    slug = [p for p in urlparse(base).path.split("/") if p]
    if slug and slug[0] not in {"profile.php", "people"} and not slug[0].isdigit():
        return f"https://www.facebook.com/{slug[0]}/posts/{post_id}"
    if profile_id:
        return f"https://www.facebook.com/permalink.php?story_fbid={post_id}&id={profile_id}"
    return f"https://www.facebook.com/{post_id}"


def list_profile_posts(profile_url: str, *, limit: int = 20) -> dict[str, Any]:
    """List recent public reel/video/post IDs from a Facebook page/profile.

    Logged-out Facebook pages expose a limited set of media IDs (best on the
    Reels tab / ``sk=reels_tab``). Use enrich=True for captions and metrics.
    """
    base = _base_profile(profile_url)
    profile_id = _profile_id_from_url(base) or _profile_id_from_url(profile_url)
    tabs = _profile_tabs(base)

    video_ids: list[str] = []
    post_ids: list[str] = []
    display_name = None
    followers = None

    for tab in tabs:
        try:
            html = fetch_html(tab) or ""
        except Exception:  # noqa: BLE001
            continue
        if not html:
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
            "username": display_name or profile_id,
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
            if pid in video_ids:
                continue
            posts.append({
                "platform": "facebook",
                "url": _post_url_for(base, pid),
                "id": pid,
                "username": display_name or profile_id,
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
        "username": display_name or profile_id or ([p for p in urlparse(base).path.split("/") if p] or [None])[0],
        "display_name": display_name,
        "followers": followers,
        "profile_url": base,
        "posts": posts[:limit],
        "count": min(len(posts), limit),
        "source": "facebook_page_tabs",
        "note": "Logged-out FB feeds are sparse; Reels tab / sk=reels_tab works best. Use enrich=True for metrics.",
    }
