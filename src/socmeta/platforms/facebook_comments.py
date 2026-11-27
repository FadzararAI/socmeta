"""Facebook comment + optional reply extraction (SSR + GraphQL replay)."""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import urlencode

from socmeta.normalize import _as_int, iso_from_timestamp
from socmeta.vendor.facebook_posts_details import config as fb_config
from socmeta.vendor.facebook_posts_details import http as fb_http
from socmeta.vendor.facebook_posts_details.http import fetch_html

# Persisted-query ids observed working for signed-out Comet (2025–2026).
# Refresh from DevTools → /api/graphql if pagination starts failing.
_COMMENTS_DOC_ID = "27806180149070312"  # CometUFICommentsProviderQuery
_REPLIES_DOC_ID = "26570577339199586"  # Depth1CommentsListPaginationQuery

_UFI_RELAY_FLAGS = {
    "__relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider": "AUTO_TRANSLATE",
    "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
    "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": True,
    "__relay_internal__pv__IsWorkUserrelayprovider": False,
}


def _extract_json_object(text: str, start: int) -> str | None:
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_json_array(text: str, start: int) -> str | None:
    if start < 0 or start >= len(text) or text[start] != "[":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _lsd_token(html: str) -> str | None:
    m = re.search(r'\["LSD",\[\],\{"token":"([^"]+)"\}', html)
    if m:
        return m.group(1)
    m = re.search(r'"LSD".{0,80}"token":"([^"]+)"', html)
    return m.group(1) if m else None


def _page_token(html: str, key: str) -> str | None:
    m = re.search(rf'"{key}"\s*:\s*"?([^",\s}}]+)"?', html)
    return m.group(1) if m else None


def _pfbid_from_url(url: str) -> str | None:
    m = re.search(r"(pfbid[0-9A-Za-z]+)", url)
    return m.group(1) if m else None


def _story_fbid_from_url(url: str) -> str | None:
    m = re.search(r"[?&]story_fbid=(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/posts/(\d+)", url)
    return m.group(1) if m else None


def _decode_b64(value: str) -> str:
    pad = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + pad).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _feedback_id_for_post(html: str, url: str) -> str | None:
    needle = _pfbid_from_url(url) or _story_fbid_from_url(url)
    for enc in set(re.findall(r'"(ZmVlZGJhY2s[^"]+)"', html)):
        dec = _decode_b64(enc)
        if needle and needle in dec:
            return enc
        if dec.startswith("feedback:") and needle and needle in dec:
            return enc
    # Fallback: first feedback id near comment_rendering_instance_for_feed_location
    i = html.find("comment_rendering_instance_for_feed_location")
    if i >= 0:
        window = html[max(0, i - 2000) : i + 5000]
        m = re.search(r'"(ZmVlZGJhY2s[^"]+)"', window)
        if m:
            return m.group(1)
    return None


def _comment_text(node: dict[str, Any]) -> str:
    for key in ("preferred_body", "body", "body_renderer"):
        val = node.get(key)
        if isinstance(val, dict) and isinstance(val.get("text"), str):
            return val["text"]
    return ""


def _username_from_author(author: dict[str, Any]) -> str | None:
    url = author.get("url") or author.get("profile_url")
    if isinstance(url, str) and "facebook.com/" in url:
        tail = url.rstrip("/").split("/")[-1]
        if tail and tail != "profile.php":
            return tail
        m = re.search(r"[?&]id=(\d+)", url)
        if m:
            return m.group(1)
    return author.get("id")


def _normalize_comment(
    node: dict[str, Any],
    *,
    parent_id: str | None = None,
) -> dict[str, Any]:
    author = node.get("author") or {}
    feedback = node.get("feedback") or {}
    replies_fields = feedback.get("replies_fields") or {}
    reactors = feedback.get("reactors") or {}
    top_reactions = feedback.get("top_reactions") or {}
    reaction_count = None
    if isinstance(top_reactions, dict):
        edges = top_reactions.get("edges") or []
        if edges:
            reaction_count = sum(_as_int((e or {}).get("reaction_count")) or 0 for e in edges)
    if reaction_count is None and isinstance(reactors, dict):
        reaction_count = _as_int(reactors.get("count"))
        if reaction_count is None:
            raw = reactors.get("count_reduced")
            if isinstance(raw, (int, float)):
                reaction_count = int(raw)
            elif isinstance(raw, str) and raw.strip().isdigit():
                reaction_count = int(raw.strip())

    row: dict[str, Any] = {
        "id": str(node.get("legacy_fbid") or node.get("id") or ""),
        "graphql_id": node.get("id"),
        "text": _comment_text(node),
        "likes": reaction_count,
        "created_at": iso_from_timestamp(node.get("created_time")),
        "username": _username_from_author(author) if isinstance(author, dict) else None,
        "display_name": author.get("name") if isinstance(author, dict) else None,
        "user_id": str(author.get("id")) if isinstance(author, dict) and author.get("id") else None,
        "profile_url": author.get("url") if isinstance(author, dict) else None,
        "reply_count": _as_int(replies_fields.get("total_count") or replies_fields.get("count")) or 0,
        "depth": _as_int(node.get("depth")) or (1 if parent_id else 0),
        "feedback_id": feedback.get("id"),
        "expansion_token": (feedback.get("expansion_info") or {}).get("expansion_token"),
    }
    if parent_id:
        row["parent_id"] = parent_id
    return row


def _edges_from_ssr(html: str) -> tuple[list[dict[str, Any]], int | None]:
    marker = '"comment_rendering_instance_for_feed_location"'
    pos = html.find(marker)
    if pos < 0:
        return [], None
    # Prefer the comments.edges under this block
    j = html.find('"edges":[', pos)
    if j < 0 or j - pos > 8000:
        return [], None
    raw = _extract_json_array(html, j + len('"edges":'))
    if not raw:
        return [], None
    try:
        edges = json.loads(raw)
    except json.JSONDecodeError:
        return [], None
    total = None
    m = re.search(r'"total_count"\s*:\s*(\d+)', html[pos : pos + 4000])
    if m:
        total = int(m.group(1))
    nodes = []
    for e in edges or []:
        node = (e or {}).get("node")
        if isinstance(node, dict):
            nodes.append(node)
    return nodes, total


def _gql_post(
    *,
    url: str,
    lsd: str,
    doc_id: str,
    friendly: str,
    variables: dict[str, Any],
    html: str,
) -> str:
    profile = fb_config.BROWSER_PROFILES[0]
    session = fb_http._get_session(profile["client_identifier"])
    headers = {
        **profile["headers"],
        "Content-Type": "application/x-www-form-urlencoded",
        "X-FB-Friendly-Name": friendly,
        "X-FB-LSD": lsd,
        "Origin": "https://www.facebook.com",
        "Referer": url.split("?")[0],
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    body: dict[str, Any] = {
        "av": "0",
        "__user": "0",
        "__a": "1",
        "__req": "1",
        "__comet_req": "15",
        "dpr": "1",
        "lsd": lsd,
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": friendly,
        "variables": json.dumps(variables, separators=(",", ":")),
        "server_timestamps": "true",
        "doc_id": str(doc_id),
    }
    jazoest = _page_token(html, "jazoest")
    rev = _page_token(html, "__spin_r") or _page_token(html, "rev")
    if not rev:
        m = re.search(r'"__spin_r"\s*,\s*\[\]\s*,\s*\{"r"\s*:\s*(\d+)', html)
        rev = m.group(1) if m else None
    if jazoest:
        body["jazoest"] = jazoest
    if rev:
        body["__rev"] = rev
        body["__spin_r"] = rev

    resp = session.post(
        "https://www.facebook.com/api/graphql/",
        headers=headers,
        data=urlencode(body),
        timeout_seconds=fb_config.DEFAULT_TIMEOUT,
    )
    return resp.text or ""


def _parse_gql_lines(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("for (;;);"):
            line = line[len("for (;;);") :].lstrip()
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _edges_to_nodes(edges: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if not isinstance(edges, list):
        return nodes
    for e in edges:
        n = (e or {}).get("node") if isinstance(e, dict) else None
        if isinstance(n, dict):
            nodes.append(n)
    return nodes


def _dig_path(obj: Any, *keys: str) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _top_level_nodes_from_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer CometUFI comments connection; avoid treating reply edges as top-level."""
    nodes: list[dict[str, Any]] = []
    for p in payloads:
        data = p.get("data") or {}
        comments = _dig_path(
            data, "node", "comment_rendering_instance_for_feed_location", "comments"
        )
        if isinstance(comments, dict) and "edges" in comments:
            nodes.extend(_edges_to_nodes(comments.get("edges")))
            continue
        # Fallback: any comments.edges under a Feedback node
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if "comments" in cur and isinstance(cur["comments"], dict):
                    edges = cur["comments"].get("edges")
                    if edges:
                        nodes.extend(_edges_to_nodes(edges))
                        break
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    return nodes


def _reply_nodes_from_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for p in payloads:
        data = p.get("data") or {}
        replies = _dig_path(data, "node", "replies_connection")
        if isinstance(replies, dict) and "edges" in replies:
            nodes.extend(_edges_to_nodes(replies.get("edges")))
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if "replies_connection" in cur and isinstance(cur["replies_connection"], dict):
                    edges = cur["replies_connection"].get("edges")
                    if edges:
                        nodes.extend(_edges_to_nodes(edges))
                        break
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    return nodes


def _page_info_from_payloads(payloads: list[dict[str, Any]]) -> tuple[str | None, bool]:
    end_cursor = None
    has_next = False
    for p in payloads:
        data = p.get("data") or {}
        comments = _dig_path(
            data, "node", "comment_rendering_instance_for_feed_location", "comments"
        )
        if isinstance(comments, dict) and isinstance(comments.get("page_info"), dict):
            pi = comments["page_info"]
            return pi.get("end_cursor"), bool(pi.get("has_next_page"))
        # generic fallback
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if "page_info" in cur and isinstance(cur["page_info"], dict):
                    pi = cur["page_info"]
                    if "has_next_page" in pi:
                        return pi.get("end_cursor"), bool(pi.get("has_next_page"))
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    return end_cursor, has_next


# Facebook UFI comment list intents (from selectable_intents on permalink).
_INTENT_NEWEST = "REVERSE_CHRONOLOGICAL_UNFILTERED_INTENT_V1"
_INTENT_RELEVANT = "RANKED_FILTERED_INTENT_V1"
_INTENT_ALL = "RANKED_UNFILTERED_CHRONOLOGICAL_REPLIES_INTENT_V1"


def _intent_for_sort(sort: str) -> str:
    key = (sort or "newest").strip().lower()
    if key in {"relevant", "relevance", "ranked"}:
        return _INTENT_RELEVANT
    if key in {"top", "likes", "best"}:
        # No dedicated "most liked" intent — unfiltered ranked list, then client likes sort.
        return _INTENT_ALL
    return _INTENT_NEWEST


def _fetch_comment_page(
    *,
    url: str,
    html: str,
    lsd: str,
    feedback_id: str,
    cursor: str | None,
    intent_token: str | None = None,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    variables = {
        "commentsAfterCount": -1,
        "commentsAfterCursor": cursor or "",
        "commentsBeforeCount": None,
        "commentsBeforeCursor": None,
        "commentsIntentToken": intent_token,
        "feedLocation": "POST_PERMALINK_DIALOG",
        "focusCommentID": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": feedback_id,
        **_UFI_RELAY_FLAGS,
    }
    text = _gql_post(
        url=url,
        lsd=lsd,
        doc_id=_COMMENTS_DOC_ID,
        friendly="CometUFICommentsProviderQuery",
        variables=variables,
        html=html,
    )
    payloads = _parse_gql_lines(text)
    if payloads and isinstance(payloads[0].get("errors"), list) and payloads[0]["errors"]:
        msg = payloads[0]["errors"][0].get("message") if isinstance(payloads[0]["errors"][0], dict) else "error"
        raise RuntimeError(f"Facebook comments GraphQL error: {msg}")
    nodes = _top_level_nodes_from_payloads(payloads)
    end_cursor, has_next = _page_info_from_payloads(payloads)
    return nodes, end_cursor, has_next


def _fetch_replies(
    *,
    url: str,
    html: str,
    lsd: str,
    feedback_id: str,
    expansion_token: str,
    limit: int,
) -> list[dict[str, Any]]:
    variables = {
        "clientKey": None,
        "expansionToken": expansion_token,
        "feedLocation": "POST_PERMALINK_DIALOG",
        "focusCommentID": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": feedback_id,
        **_UFI_RELAY_FLAGS,
    }
    text = _gql_post(
        url=url,
        lsd=lsd,
        doc_id=_REPLIES_DOC_ID,
        friendly="Depth1CommentsListPaginationQuery",
        variables=variables,
        html=html,
    )
    payloads = _parse_gql_lines(text)
    if payloads and isinstance(payloads[0].get("errors"), list) and payloads[0]["errors"]:
        msg = payloads[0]["errors"][0].get("message") if isinstance(payloads[0]["errors"][0], dict) else "error"
        raise RuntimeError(f"Facebook replies GraphQL error: {msg}")
    nodes = _reply_nodes_from_payloads(payloads)
    return nodes[:limit]


def list_facebook_comments(
    url: str,
    *,
    limit: int = 50,
    include_replies: bool = False,
    replies_limit: int = 20,
    sort: str = "newest",
) -> dict[str, Any]:
    """Fetch public comments for a Facebook post URL.

    Uses the permalink SSR payload (relevant only), then GraphQL pagination
    with a sort-matched ``commentsIntentToken``. Replies are optional
    (``include_replies=False`` by default).
    """
    html = fetch_html(url)
    if not html:
        raise RuntimeError(f"Facebook returned no HTML for {url}")

    lsd = _lsd_token(html)
    feedback_id = _feedback_id_for_post(html, url)
    ssr_nodes, total = _edges_from_ssr(html)
    intent = _intent_for_sort(sort)
    # SSR embed is FB's "Most relevant" slice — only seed from it for relevant.
    use_ssr = intent == _INTENT_RELEVANT

    raw_nodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_nodes(nodes: list[dict[str, Any]]) -> None:
        for n in nodes:
            key = str(n.get("legacy_fbid") or n.get("id") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            raw_nodes.append(n)

    if use_ssr:
        add_nodes(ssr_nodes)

    cursor: str | None = None
    # Continue via GraphQL when we need more / have feedback id.
    # First GraphQL page often overlaps SSR; keep advancing via end_cursor.
    if feedback_id and lsd and len(raw_nodes) < limit:
        has_next = True
        pages = 0
        while len(raw_nodes) < limit and has_next and pages < 40:
            try:
                nodes, next_cursor, has_next = _fetch_comment_page(
                    url=url,
                    html=html,
                    lsd=lsd,
                    feedback_id=feedback_id,
                    cursor=cursor,
                    intent_token=intent,
                )
            except Exception:
                break
            add_nodes(nodes)
            pages += 1
            if not has_next:
                break
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

    raw_nodes = raw_nodes[:limit]
    comments: list[dict[str, Any]] = []
    replies_fetched = 0

    for node in raw_nodes:
        row = _normalize_comment(node)
        # Strip internal pagination helpers from public output later
        if include_replies and row.get("reply_count", 0) > 0 and row.get("feedback_id") and row.get("expansion_token") and lsd:
            try:
                reply_nodes = _fetch_replies(
                    url=url,
                    html=html,
                    lsd=lsd,
                    feedback_id=row["feedback_id"],
                    expansion_token=row["expansion_token"],
                    limit=replies_limit,
                )
                replies = [
                    _normalize_comment(rn, parent_id=row["id"])
                    for rn in reply_nodes
                ]
                # Clean internal fields on replies
                for r in replies:
                    r.pop("feedback_id", None)
                    r.pop("expansion_token", None)
                    r.pop("graphql_id", None)
                row["replies"] = replies
                replies_fetched += len(replies)
            except Exception as exc:  # noqa: BLE001
                row["replies"] = []
                row["replies_error"] = f"{type(exc).__name__}: {exc}"
        row.pop("feedback_id", None)
        row.pop("expansion_token", None)
        row.pop("graphql_id", None)
        comments.append(row)

    note = "Top-level comments only." if not include_replies else (
        f"Top-level comments + replies (up to {replies_limit} per comment)."
    )
    note += f" Intent={intent}."
    if total is not None and len(comments) < total and not include_replies:
        note += f" Post reports ~{total} comments."

    return {
        "platform": "facebook",
        "url": url.split("?")[0] if "story_fbid=" not in url else url,
        "id": _pfbid_from_url(url) or _story_fbid_from_url(url),
        "comments": comments,
        "count": len(comments),
        "total": total,
        "include_replies": include_replies,
        "replies_fetched": replies_fetched if include_replies else None,
        "source": "facebook-ssr+graphql",
        "note": note,
        "status": "ok",
    }
