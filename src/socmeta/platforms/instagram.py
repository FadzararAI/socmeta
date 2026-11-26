"""Instagram profile followers + recent posts from the public profile page."""

from __future__ import annotations

import json
import re
from typing import Any

from curl_cffi import requests as crequests

_IG_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "X-IG-App-ID": "936619743392459",
}


def profile_followers(username: str) -> int | None:
    r = crequests.get(
        f"https://www.instagram.com/{username.lstrip('@')}/",
        impersonate="chrome",
        timeout=30,
        headers=_IG_HEADERS,
    )
    hits = [int(x) for x in re.findall(r'"follower_count"\s*:\s*(\d+)', r.text)]
    return hits[0] if hits else None


def _caption_text(node: dict[str, Any]) -> str | None:
    cap = node.get("caption")
    if isinstance(cap, dict):
        return cap.get("text")
    if isinstance(cap, str):
        return cap
    return None


def _pk_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(str(value).split("_")[0])
    except (TypeError, ValueError):
        return 0


def _path_for_media(node: dict[str, Any]) -> str:
    """Prefer /p/ for feed posts/carousels; /reel/ for clips."""
    seo = node.get("seo_canonical_url")
    if isinstance(seo, str):
        if "/reel/" in seo or "/reels/" in seo:
            return "reel"
        if "/p/" in seo:
            return "p"
    product = node.get("product_type")
    media_type = node.get("media_type")
    if product in {"clips", "reel", "reels"}:
        return "reel"
    if product == "carousel_container" or media_type in {1, 8}:
        return "p"
    if media_type == 2:
        return "reel"
    return "p"


def _walk_media(data: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            code = node.get("code") or node.get("shortcode")
            if (
                isinstance(code, str)
                and 8 <= len(code) <= 20
                and code != "en_US"
                and ("caption" in node or "media_type" in node or "product_type" in node)
                and (node.get("pk") or node.get("id"))
            ):
                found.append({
                    "code": code,
                    "path": _path_for_media(node),
                    "like_count": node.get("like_count"),
                    "comment_count": node.get("comment_count"),
                    "taken_at": node.get("taken_at") or node.get("taken_at_ts"),
                    "media_type": node.get("media_type"),
                    "product_type": node.get("product_type"),
                    "caption": _caption_text(node),
                    "pk": node.get("pk") or node.get("id"),
                    "user": node.get("user") if isinstance(node.get("user"), dict) else None,
                })
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def list_profile_posts(username: str, *, limit: int = 12) -> dict[str, Any]:
    """Return recent posts embedded on a logged-out Instagram profile page.

    Posts are sorted newest-first by media id (``pk``). The page typically
    embeds ~12 grid items (including older pinned posts).
    """
    handle = username.lstrip("@")
    session = crequests.Session(impersonate="chrome")
    resp = session.get(
        f"https://www.instagram.com/{handle}/",
        timeout=30,
        headers=_IG_HEADERS,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Instagram profile HTTP {resp.status_code}")

    followers = None
    hits = [int(x) for x in re.findall(r'"follower_count"\s*:\s*(\d+)', resp.text)]
    if hits:
        followers = hits[0]

    blobs = re.findall(r'<script type="application/json"[^>]*>(.*?)</script>', resp.text, re.S)
    media: list[dict[str, Any]] = []
    for raw in blobs:
        if '"code"' not in raw and "shortcode" not in raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        media.extend(_walk_media(data))

    # Dedupe by code, keep richest node (prefer one with caption)
    by_code: dict[str, dict[str, Any]] = {}
    for m in media:
        code = m["code"]
        prev = by_code.get(code)
        if prev is None or (m.get("caption") and not prev.get("caption")):
            by_code[code] = m

    ordered = sorted(by_code.values(), key=lambda m: _pk_int(m.get("pk")), reverse=True)

    posts: list[dict[str, Any]] = []
    display_name = None
    for m in ordered[:limit]:
        user = m.get("user") or {}
        if not display_name:
            display_name = user.get("full_name")
        path = m["path"]
        code = m["code"]
        posts.append({
            "platform": "instagram",
            "url": f"https://www.instagram.com/{path}/{code}/",
            "id": code,
            "username": user.get("username") or handle,
            "display_name": user.get("full_name") or display_name,
            "caption": m.get("caption"),
            "likes": m.get("like_count"),
            "comments": m.get("comment_count"),
            "reposts": None,
            "shares": None,
            "bookmarks": None,
            "views": None,
            "post_date": None,
            "media_type": m.get("media_type"),
            "product_type": m.get("product_type"),
            "status": "ok",
        })

    return {
        "platform": "instagram",
        "username": handle,
        "display_name": display_name,
        "followers": followers,
        "profile_url": f"https://www.instagram.com/{handle}/",
        "posts": posts,
        "count": len(posts),
        "source": "instagram_profile_page",
        "note": "Sorted newest-first by media id. Logged-out pages embed ~12 grid items; use enrich=True for likes/comments.",
    }
