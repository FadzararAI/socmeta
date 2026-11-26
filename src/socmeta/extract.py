"""Unified entry: ``extract(url)`` → normalized post metadata."""

from __future__ import annotations

from typing import Any

from .detect import detect_platform
from .followers import enrich_followers


def extract(
    url: str,
    *,
    enrich: bool = True,
    cookies_from_browser: str | None = None,
    cookiefile: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Extract public metadata for a social post URL.

    Platforms: YouTube, Facebook, TikTok, X, Instagram, Threads.

    When ``enrich`` is True (default), resolve author followers via
    post-embedded fields or a profile lookup (post → author → followers).
    """
    platform = detect_platform(url)
    if platform is None:
        raise ValueError(f"Unsupported or unrecognized social URL: {url}")

    if platform == "facebook":
        from .platforms.facebook import extract_facebook

        try:
            row = extract_facebook(url, with_profile=True)
        except Exception:
            # Fallback to yt-dlp for some video/reel URLs
            from .platforms.ytdlp import extract_via_ytdlp

            row = extract_via_ytdlp(
                url,
                platform=platform,
                cookies_from_browser=cookies_from_browser,
                cookiefile=cookiefile,
                verbose=verbose,
            )
    elif platform == "threads":
        from .platforms.threads import extract_threads

        row = extract_threads(url)
    else:
        from .platforms.ytdlp import extract_via_ytdlp

        row = extract_via_ytdlp(
            url,
            platform=platform,
            cookies_from_browser=cookies_from_browser,
            cookiefile=cookiefile,
            verbose=verbose,
        )

    if enrich:
        row = enrich_followers(row)
    else:
        from .followers import author_from_post

        author = author_from_post(row)
        row["author"] = author
        row["author_profile"] = author.get("profile_url")

    row.setdefault("status", "ok")
    return row


def extract_many(urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for url in urls:
        try:
            results.append(extract(url, **kwargs))
        except Exception as exc:  # noqa: BLE001
            results.append({
                "platform": detect_platform(url),
                "url": url,
                "status": "fail",
                "error": f"{type(exc).__name__}: {exc}",
            })
    return results
