"""Instagram comment extraction (logged-out permalink + GraphQL pagination)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode, urlparse

from curl_cffi import requests as crequests

from socmeta.normalize import _as_int, iso_from_timestamp

_IG_APP_ID = "936619743392459"
# PolarisLoggedOutDesktopWWWPostCommentsPaginationQuery (rotates periodically)
_COMMENTS_DOC_ID = "27261273046856309"
_COMMENTS_FRIENDLY = "PolarisLoggedOutDesktopWWWPostCommentsPaginationQuery"


def shortcode_from_url(url: str) -> str | None:
    parts = [p for p in urlparse(url).path.split("/") if p]
    for i, p in enumerate(parts):
        if p in {"p", "reel", "reels", "tv"} and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _lsd_token(html: str) -> str | None:
    m = re.search(r'\["LSD",\[\],\{"token":"([^"]+)"\}', html)
    return m.group(1) if m else None


def _page_blobs(html: str) -> list[Any]:
    blobs = []
    for raw in re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.S):
        try:
            blobs.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blobs


def _media_from_blobs(blobs: list[Any], shortcode: str) -> dict[str, Any] | None:
    for blob in blobs:
        for n in _walk(blob):
            if not isinstance(n, dict):
                continue
            if n.get("code") == shortcode and (n.get("pk") or n.get("id")):
                if "comments_connection" in n or "comment_count" in n or "user" in n:
                    return n
    return None


def _normalize(node: dict[str, Any], *, parent_id: str | None = None) -> dict[str, Any]:
    user = node.get("user") or {}
    username = user.get("username")
    row: dict[str, Any] = {
        "id": str(node.get("pk") or node.get("id") or ""),
        "text": node.get("text") or "",
        "likes": _as_int(node.get("comment_like_count")),
        "created_at": iso_from_timestamp(node.get("created_at")),
        "username": username,
        "display_name": user.get("full_name") or username,
        "user_id": str(user.get("pk") or user.get("id") or "") or None,
        "profile_url": f"https://www.instagram.com/{username}/" if username else None,
        "reply_count": _as_int(node.get("child_comment_count")) or 0,
    }
    if parent_id:
        row["parent_id"] = parent_id
    return row


def _session(url: str):
    s = crequests.Session(impersonate="chrome")
    headers = {
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": _IG_APP_ID,
        "Referer": url.split("?")[0],
    }
    resp = s.get(url.split("?")[0], headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Instagram post HTTP {resp.status_code}")
    return s, resp.text, headers


def _gql_comments_page(
    session,
    *,
    url: str,
    html: str,
    media_id: str,
    after: str | None,
    first: int,
) -> dict[str, Any]:
    lsd = _lsd_token(html)
    csrf = session.cookies.get("csrftoken") or ""
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.instagram.com",
        "Referer": url.split("?")[0],
        "X-CSRFToken": csrf,
        "X-FB-Friendly-Name": _COMMENTS_FRIENDLY,
        "X-FB-LSD": lsd or "",
        "X-IG-App-ID": _IG_APP_ID,
        "X-Requested-With": "XMLHttpRequest",
    }
    variables = {"media_id": str(media_id), "first": int(first), "after": after}
    body = {
        "lsd": lsd or "",
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": _COMMENTS_FRIENDLY,
        "variables": json.dumps(variables, separators=(",", ":")),
        "server_timestamps": "true",
        "doc_id": _COMMENTS_DOC_ID,
    }
    resp = session.post(
        "https://www.instagram.com/api/graphql",
        data=urlencode(body),
        headers=headers,
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Instagram comments GraphQL HTTP {resp.status_code}: {resp.text[:160]}")
    data = resp.json()
    if data.get("status") == "fail" or data.get("require_login"):
        raise RuntimeError(data.get("message") or "Instagram comments require login")
    return ((data.get("data") or {}).get("xig_polaris_media") or {}).get("comments_connection") or {}


def list_instagram_comments(
    url: str,
    *,
    limit: int = 50,
    include_replies: bool = False,
    replies_limit: int = 20,
) -> dict[str, Any]:
    """Fetch public comments for an Instagram post/reel URL.

    Logged-out Instagram typically exposes only the first ~12–50 parent
    comments; the remainder may sit behind a login wall. Replies are not
    expanded yet (``include_replies`` reserved for compatibility).
    """
    shortcode = shortcode_from_url(url)
    if not shortcode:
        raise ValueError(f"Could not parse Instagram shortcode from URL: {url}")

    session, html, _ = _session(url)
    blobs = _page_blobs(html)
    media = _media_from_blobs(blobs, shortcode)
    if not media:
        raise RuntimeError(f"Instagram post not found or not public: {url}")

    media_id = str(media.get("pk") or media.get("id") or "")
    total = _as_int(media.get("comment_count"))
    if total is None:
        # comment_count often lives on a sibling media dict with the same pk/code
        for blob in blobs:
            for n in _walk(blob):
                if (
                    isinstance(n, dict)
                    and (n.get("code") == shortcode or str(n.get("pk") or "") == media_id)
                    and n.get("comment_count") is not None
                ):
                    total = _as_int(n.get("comment_count"))
                    break
            if total is not None:
                break
    ssr_conn = media.get("comments_connection") if isinstance(media.get("comments_connection"), dict) else {}

    raw_nodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_edges(edges: Any) -> None:
        if not isinstance(edges, list):
            return
        for e in edges:
            n = (e or {}).get("node") if isinstance(e, dict) else None
            if not isinstance(n, dict):
                continue
            pk = str(n.get("pk") or n.get("id") or "")
            if pk and pk in seen:
                continue
            if pk:
                seen.add(pk)
            raw_nodes.append(n)

    add_edges((ssr_conn or {}).get("edges"))

    # GraphQL: start from after=None to pull the largest first page, then cursor.
    after: str | None = None
    pages = 0
    login_gated = False
    while len(raw_nodes) < limit and pages < 40:
        try:
            conn = _gql_comments_page(
                session,
                url=url,
                html=html,
                media_id=media_id,
                after=after,
                first=min(50, max(limit - len(raw_nodes), 12)),
            )
        except Exception as exc:  # noqa: BLE001
            if "login" in str(exc).lower() or "wait a few minutes" in str(exc).lower():
                login_gated = True
            break
        before = len(raw_nodes)
        add_edges(conn.get("edges"))
        pages += 1
        pi = conn.get("page_info") or {}
        if not pi.get("has_next_page") or not pi.get("end_cursor"):
            break
        if len(raw_nodes) == before:
            break
        after = pi.get("end_cursor")

    raw_nodes = raw_nodes[:limit]
    comments = [_normalize(n) for n in raw_nodes]
    if include_replies:
        # Child comments are not reliably exposed logged-out yet.
        for c in comments:
            c.setdefault("replies", [])

    note = "Top-level comments (logged-out Instagram)."
    if include_replies:
        note += " Nested replies not expanded yet for Instagram."
    if total is not None and len(comments) < total:
        note += f" Fetched {len(comments)} of ~{total}; remaining comments may require login."
    if login_gated:
        note += " Further pages were login-gated."

    return {
        "platform": "instagram",
        "url": url.split("?")[0],
        "id": shortcode,
        "media_id": media_id,
        "comments": comments,
        "count": len(comments),
        "total": total,
        "include_replies": include_replies,
        "replies_fetched": 0 if include_replies else None,
        "source": "instagram-ssr+graphql",
        "note": note,
        "status": "ok",
    }
