"""Profile → recent posts listing across platforms."""

from __future__ import annotations

from typing import Any

from .profile_ref import resolve_profile


def profile_posts(
    ref: str,
    *,
    platform: str | None = None,
    limit: int = 20,
    enrich: bool = False,
    cookies_from_browser: str | None = None,
    cookiefile: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """List recent public posts for a profile URL or @handle.

    Parameters
    ----------
    ref:
        Profile URL (``https://www.tiktok.com/@user``) or bare handle
        (requires ``platform``).
    limit:
        Max posts to return (platform caps may be lower, e.g. IG ~12).
    enrich:
        When True, re-scrape each post URL for full engagement metrics
        (slower; useful when the feed listing omits likes/comments).
    """
    resolved = resolve_profile(ref, platform=platform)
    plat = resolved["platform"]
    username = resolved["username"]
    profile_url = resolved["profile_url"]

    if plat in {"youtube", "tiktok"}:
        from .platforms.ytdlp import list_via_ytdlp

        result = list_via_ytdlp(
            profile_url,
            platform=plat,
            username=username,
            limit=limit,
            cookies_from_browser=cookies_from_browser,
            cookiefile=cookiefile,
            verbose=verbose,
        )
    elif plat == "x":
        from .platforms.x import list_profile_posts as list_x

        result = list_x(username, limit=limit)
    elif plat == "instagram":
        from .platforms.instagram import list_profile_posts as list_ig

        result = list_ig(username, limit=limit)
    elif plat == "threads":
        from .platforms.threads import list_profile_posts as list_threads

        result = list_threads(username, limit=limit)
    elif plat == "facebook":
        from .platforms.facebook import list_profile_posts as list_fb

        result = list_fb(profile_url, limit=limit)
    else:
        raise ValueError(f"Unsupported platform for profile feeds: {plat}")

    result.setdefault("profile_url", profile_url)
    result.setdefault("username", username)
    result["status"] = "ok"

    if enrich and result.get("posts"):
        from .extract import extract

        enriched: list[dict[str, Any]] = []
        for post in result["posts"]:
            url = post.get("url")
            if not url:
                enriched.append(post)
                continue
            try:
                full = extract(
                    url,
                    enrich=True,
                    cookies_from_browser=cookies_from_browser,
                    cookiefile=cookiefile,
                    verbose=verbose,
                )
                # Keep feed-level fields when full extract blanks them
                for key in ("username", "display_name", "id"):
                    full.setdefault(key, post.get(key))
                enriched.append(full)
            except Exception as exc:  # noqa: BLE001
                row = dict(post)
                row["status"] = "fail"
                row["error"] = f"{type(exc).__name__}: {exc}"
                enriched.append(row)
        result["posts"] = enriched
        result["enriched"] = True

    return result
