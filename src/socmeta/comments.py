"""Unified comment extraction across platforms."""

from __future__ import annotations

from typing import Any

from .comment_sort import CommentSort, apply_comment_sort, normalize_sort
from .detect import detect_platform


def extract_comments(
    url: str,
    *,
    limit: int = 50,
    include_replies: bool = False,
    replies_limit: int = 20,
    sort: CommentSort | str = "newest",
    ranking_mode: str | None = None,
) -> dict[str, Any]:
    """Extract public comments for a post URL.

    ``sort``: ``newest`` (default), ``top`` (by likes), or ``relevant``
    (platform ranking when available).
    ``include_replies`` defaults to False — top-level comments only.
    ``ranking_mode`` optionally overrides X fetch ranking: ``recency`` or ``likes``.
    """
    sort = normalize_sort(sort)
    platform = detect_platform(url)
    if platform is None:
        raise ValueError(f"Unsupported or unrecognized social URL: {url}")

    if platform == "tiktok":
        from .platforms.tiktok_comments import list_tiktok_comments

        result = list_tiktok_comments(
            url,
            limit=limit,
            include_replies=include_replies,
            replies_limit=replies_limit,
        )
    elif platform == "facebook":
        from .platforms.facebook_comments import list_facebook_comments

        result = list_facebook_comments(
            url,
            limit=limit,
            include_replies=include_replies,
            replies_limit=replies_limit,
            sort=sort,
        )
    elif platform == "threads":
        from .platforms.threads_comments import list_threads_comments

        result = list_threads_comments(
            url,
            limit=limit,
            include_replies=include_replies,
            replies_limit=replies_limit,
        )
    elif platform == "instagram":
        from .platforms.instagram_comments import list_instagram_comments

        result = list_instagram_comments(
            url,
            limit=limit,
            include_replies=include_replies,
            replies_limit=replies_limit,
        )
    elif platform == "x":
        from .platforms.x_comments import list_x_comments

        if ranking_mode:
            mode = ranking_mode.lower()
        elif sort == "newest":
            mode = "recency"
        else:
            mode = "likes"
        if mode not in {"likes", "recency"}:
            mode = "recency"
        result = list_x_comments(
            url,
            limit=limit,
            include_replies=include_replies,
            replies_limit=replies_limit,
            ranking_mode=mode,  # type: ignore[arg-type]
        )
    elif platform == "youtube":
        from .platforms.youtube_comments import list_youtube_comments

        result = list_youtube_comments(
            url,
            limit=limit,
            include_replies=include_replies,
            replies_limit=replies_limit,
            sort=sort,
        )
    else:
        raise NotImplementedError(
            f"Comment extraction is not implemented yet for platform={platform!r}. "
            "Supported: youtube, tiktok, facebook, threads, instagram, x."
        )

    return apply_comment_sort(result, sort)


def extract_comments_many(urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
    """Extract comments for multiple post URLs (failures become ``status: fail`` rows)."""
    results: list[dict[str, Any]] = []
    for url in urls:
        try:
            results.append(extract_comments(url, **kwargs))
        except Exception as exc:  # noqa: BLE001
            results.append({
                "platform": detect_platform(url),
                "url": url,
                "comments": [],
                "count": 0,
                "status": "fail",
                "error": f"{type(exc).__name__}: {exc}",
            })
    return results
