"""TikTok comment + optional reply extraction via the public web API."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from curl_cffi import requests as crequests

from socmeta.normalize import _as_int, iso_from_timestamp

_VIDEO_ID_RE = re.compile(r"/video/(\d+)", re.I)

_COMMENT_LIST = "https://www.tiktok.com/api/comment/list/"
_REPLY_LIST = "https://www.tiktok.com/api/comment/list/reply/"


def aweme_id_from_url(url: str) -> str | None:
    m = _VIDEO_ID_RE.search(urlparse(url).path or url)
    return m.group(1) if m else None


def _session(url: str):
    headers = {
        "Referer": url.split("?")[0],
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }
    s = crequests.Session(impersonate="chrome")
    # Warm cookies / session from the video page (best-effort).
    try:
        s.get(url.split("?")[0], headers=headers, timeout=30)
    except Exception:  # noqa: BLE001
        pass
    return s, headers


def _normalize_comment(raw: dict[str, Any], *, parent_id: str | None = None) -> dict[str, Any]:
    user = raw.get("user") or {}
    username = user.get("unique_id") or user.get("uniqueId")
    row: dict[str, Any] = {
        "id": str(raw.get("cid") or raw.get("comment_id") or ""),
        "text": raw.get("text") or "",
        "likes": _as_int(raw.get("digg_count")),
        "created_at": iso_from_timestamp(raw.get("create_time")),
        "username": username,
        "display_name": user.get("nickname"),
        "user_id": str(user.get("uid") or "") or None,
        "author_liked": bool(raw.get("is_author_digged")),
        "reply_count": _as_int(raw.get("reply_comment_total")) or 0,
        "language": raw.get("comment_language"),
    }
    if parent_id:
        row["parent_id"] = parent_id
    labels = raw.get("label_list") or []
    if isinstance(labels, list) and labels:
        row["labels"] = [x.get("text") for x in labels if isinstance(x, dict) and x.get("text")]
    return row


def _fetch_page(
    session,
    headers: dict[str, str],
    *,
    endpoint: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    resp = session.get(endpoint, params=params, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"TikTok comments HTTP {resp.status_code}")
    data = resp.json()
    if data.get("status_code") not in (0, None, "0"):
        # Some responses omit status_code when ok; only fail on explicit errors.
        if data.get("status_code") not in (0, "0") and "comments" not in data:
            raise RuntimeError(
                f"TikTok comments error: {data.get('status_msg') or data.get('status_code')}"
            )
    return data


def _paginate(
    session,
    headers: dict[str, str],
    *,
    endpoint: str,
    base_params: dict[str, Any],
    limit: int,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int | None]:
    out: list[dict[str, Any]] = []
    cursor = 0
    total: int | None = None
    seen: set[str] = set()

    while len(out) < limit:
        count = min(page_size, limit - len(out))
        params = {**base_params, "cursor": cursor, "count": count}
        data = _fetch_page(session, headers, endpoint=endpoint, params=params)
        if total is None:
            total = _as_int(data.get("total"))
        batch = data.get("comments") or []
        if not batch:
            break
        for raw in batch:
            cid = str(raw.get("cid") or "")
            if cid and cid in seen:
                continue
            if cid:
                seen.add(cid)
            out.append(raw)
            if len(out) >= limit:
                break
        if not data.get("has_more"):
            break
        next_cursor = data.get("cursor")
        if next_cursor is None or next_cursor == cursor:
            break
        cursor = next_cursor
    return out, total


def fetch_replies(
    session,
    headers: dict[str, str],
    *,
    aweme_id: str,
    comment_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    raws, _ = _paginate(
        session,
        headers,
        endpoint=_REPLY_LIST,
        base_params={"aid": "1988", "item_id": aweme_id, "comment_id": comment_id},
        limit=limit,
    )
    return [_normalize_comment(r, parent_id=comment_id) for r in raws]


def list_tiktok_comments(
    url: str,
    *,
    limit: int = 50,
    include_replies: bool = False,
    replies_limit: int = 20,
) -> dict[str, Any]:
    """Fetch top-level comments for a TikTok video URL.

    Parameters
    ----------
    limit:
        Max top-level comments to return.
    include_replies:
        When True, also fetch replies under each comment (capped by
        ``replies_limit`` per parent). Default False.
    replies_limit:
        Max replies per parent comment when ``include_replies`` is True.
    """
    aweme_id = aweme_id_from_url(url)
    if not aweme_id:
        raise ValueError(f"Could not parse TikTok video id from URL: {url}")

    session, headers = _session(url)
    raws, total = _paginate(
        session,
        headers,
        endpoint=_COMMENT_LIST,
        base_params={"aid": "1988", "aweme_id": aweme_id},
        limit=limit,
    )

    comments: list[dict[str, Any]] = []
    reply_fetched = 0
    for raw in raws:
        row = _normalize_comment(raw)
        if include_replies and (row.get("reply_count") or 0) > 0 and row.get("id"):
            try:
                replies = fetch_replies(
                    session,
                    headers,
                    aweme_id=aweme_id,
                    comment_id=row["id"],
                    limit=replies_limit,
                )
                row["replies"] = replies
                reply_fetched += len(replies)
            except Exception as exc:  # noqa: BLE001
                row["replies"] = []
                row["replies_error"] = f"{type(exc).__name__}: {exc}"
        comments.append(row)

    note = "Top-level comments only." if not include_replies else (
        f"Top-level comments + replies (up to {replies_limit} per comment)."
    )
    return {
        "platform": "tiktok",
        "url": url.split("?")[0],
        "id": aweme_id,
        "comments": comments,
        "count": len(comments),
        "total": total,
        "include_replies": include_replies,
        "replies_fetched": reply_fetched if include_replies else None,
        "source": "tiktok-web-api",
        "note": note,
        "status": "ok",
    }
