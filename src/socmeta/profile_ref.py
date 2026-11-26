"""Resolve a profile URL or @handle into (platform, username, profile_url)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .detect import detect_platform

_HANDLE_RE = re.compile(r"^@?[A-Za-z0-9._]+$")


def _username_from_path(platform: str, path: str) -> str | None:
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    if platform == "youtube":
        # /@handle, /channel/UC..., /c/name, /user/name
        if parts[0].startswith("@"):
            return parts[0]
        if parts[0] in {"channel", "c", "user"} and len(parts) >= 2:
            return parts[1]
        return parts[0]
    if platform == "tiktok":
        for p in parts:
            if p.startswith("@"):
                return p.lstrip("@")
        return None
    if platform == "x":
        skip = {"home", "explore", "search", "i", "intent", "settings"}
        if parts[0] in skip:
            return None
        if parts[0] == "status":
            return None
        return parts[0].lstrip("@")
    if platform == "instagram":
        skip = {"p", "reel", "reels", "stories", "explore", "accounts", "tv"}
        if parts[0] in skip:
            return None
        return parts[0].lstrip("@")
    if platform == "threads":
        for p in parts:
            if p.startswith("@"):
                return p.lstrip("@")
        return None
    if platform == "facebook":
        skip = {"reel", "reels", "watch", "story", "stories", "photo", "photos", "video", "videos", "posts", "people", "profile.php"}
        if parts[0] == "profile.php":
            return None
        if parts[0] == "people" and len(parts) >= 2:
            return parts[1]
        if parts[0] in skip:
            return None
        return parts[0]
    return parts[0].lstrip("@")


def profile_url_for(platform: str, username: str) -> str:
    u = username.lstrip("@")
    if platform == "youtube":
        if u.startswith("UC") and len(u) >= 20:
            return f"https://www.youtube.com/channel/{u}/videos"
        if u.startswith("@"):
            return f"https://www.youtube.com/{u}/videos"
        return f"https://www.youtube.com/@{u}/videos"
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{u}"
    if platform == "x":
        return f"https://x.com/{u}"
    if platform == "instagram":
        return f"https://www.instagram.com/{u}/"
    if platform == "threads":
        return f"https://www.threads.com/@{u}"
    if platform == "facebook":
        if u.isdigit():
            return f"https://www.facebook.com/profile.php?id={u}"
        return f"https://www.facebook.com/{u}"
    raise ValueError(f"Unsupported platform: {platform}")


def resolve_profile(ref: str, *, platform: str | None = None) -> dict[str, str]:
    """Accept a profile URL or bare @handle (+ platform)."""
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("Empty profile reference")

    looks_like_url = "://" in ref or ref.startswith("www.")
    if looks_like_url:
        if ref.startswith("www."):
            ref = "https://" + ref
        plat = platform or detect_platform(ref)
        if not plat:
            raise ValueError(f"Unrecognized profile URL: {ref}")
        path = urlparse(ref).path
        username = _username_from_path(plat, path)
        if not username:
            # Facebook numeric profile.php?id=
            if plat == "facebook" and "id=" in ref:
                m = re.search(r"[?&]id=(\d+)", ref)
                username = m.group(1) if m else None
        if not username:
            raise ValueError(f"Could not parse username from profile URL: {ref}")
        return {
            "platform": plat,
            "username": username.lstrip("@"),
            "profile_url": profile_url_for(plat, username),
        }

    # bare handle
    handle = ref.lstrip("@").strip().strip("/")
    if not platform:
        raise ValueError(
            "Bare @handle requires --platform (youtube|tiktok|x|instagram|threads|facebook)"
        )
    platform = platform.lower().strip()
    if platform == "twitter":
        platform = "x"
    if platform not in {"youtube", "tiktok", "x", "instagram", "threads", "facebook"}:
        raise ValueError(f"Unsupported platform: {platform}")
    if not _HANDLE_RE.match(handle) and not (platform == "facebook" and handle.isdigit()):
        # allow youtube channel ids / @handles already stripped
        if platform != "youtube":
            raise ValueError(f"Invalid handle: {ref}")
    return {
        "platform": platform,
        "username": handle.lstrip("@"),
        "profile_url": profile_url_for(platform, handle),
    }
