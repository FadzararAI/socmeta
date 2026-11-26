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
                product = node.get("product_type")
                path = "reel" if product in {"clips", "reel", "reels"} or node.get("media_type") == 2 else "p"
                # clips/reels often media_type 2; carousels/photos use /p/
                if product == "carousel_container" or node.get("media_type") in {1, 8}:
                    path = "p"
                elif product in {"clips", "reel", "reels"}:
                    path = "reel"
                found.append({
                    "code": code,
                    "path": path,
                    "like_count": node.get("like_count"),
                    "comment_count": node.get("comment_count"),
                    "taken_at": node.get("taken_at") or node.get("taken_at_ts"),
                    "media_type": node.get("media_type"),
                    "product_type": product,
                    "caption": _caption_text(node),
                    "pk": node.get("pk") or node.get("id"),
                    "user": node.get("user") if isinstance(node.get("user"), dict) else None,
                })
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def list_profile_posts(username: str, *, limit: int = 12) -> dict[str, Any]:
    """Return the posts embedded on a logged-out Instagram profile page (~12)."""
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

    seen: set[str] = set()
    posts: list[dict[str, Any]] = []
    display_name = None
    for m in media:
        code = m["code"]
        if code in seen:
            continue
        seen.add(code)
        user = m.get("user") or {}
        if not display_name:
            display_name = user.get("full_name")
        path = m["path"]
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
        if len(posts) >= limit:
            break

    return {
        "platform": "instagram",
        "username": handle,
        "display_name": display_name,
        "followers": followers,
        "profile_url": f"https://www.instagram.com/{handle}/",
        "posts": posts[:limit],
        "count": min(len(posts), limit),
        "source": "instagram_profile_page",
        "note": "Logged-out profile pages usually embed ~12 recent posts; likes/comments often need enrich=True.",
    }
