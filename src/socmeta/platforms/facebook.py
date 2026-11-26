"""Facebook post/profile adapter.

Uses the vendored ``facebook_posts_details`` library (MIT, Aman / binarykernal)
for single-post scraping, plus logged-out ``ProfileCometTimelineFeedQuery`` for
profile timeline feeds (posts + reels).
See ``socmeta/vendor/facebook_posts_details/LICENSE``.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode, urlparse

from socmeta.normalize import iso_from_timestamp
from socmeta.vendor import facebook_posts_details as fb
from socmeta.vendor.facebook_posts_details import config as fb_config
from socmeta.vendor.facebook_posts_details import http as fb_http
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


def _extract_json_object(text: str, start: int) -> str | None:
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _timeline_preloader(html: str) -> tuple[str, dict[str, Any]] | None:
    m = re.search(
        r'ProfileCometTimelineFeedQueryRelayPreloader_[^"]+"\s*,\s*"queryID"\s*:\s*"(\d+)"\s*,\s*"variables"\s*:\s*(\{)',
        html,
    )
    if not m:
        return None
    raw = _extract_json_object(html, m.start(2))
    if not raw:
        return None
    try:
        variables = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return m.group(1), variables


def _lsd_token(html: str) -> str | None:
    m = re.search(r'\["LSD",\[\],\{"token":"([^"]+)"\}', html)
    if m:
        return m.group(1)
    m = re.search(r'"LSD".{0,80}"token":"([^"]+)"', html)
    return m.group(1) if m else None


def _walk_caption(node: Any) -> str | None:
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            msg = cur.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("text"), str):
                return msg["text"]
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def _walk_urls(node: Any) -> list[str]:
    urls: list[str] = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for key in ("wwwURL", "url", "permalink_url"):
                val = cur.get(key)
                if isinstance(val, str) and "facebook.com" in val and "comment_id=" not in val:
                    urls.append(val)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    # prefer stable canonical forms
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        clean = u.split("?")[0] if "/reel/" in u else u
        if clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _best_post_url(urls: list[str], *, profile_id: str | None, post_id: str | None) -> str | None:
    reel = next((u for u in urls if "/reel/" in u), None)
    if reel:
        return reel.rstrip("/")
    permalink = next(
        (u for u in urls if "story_fbid=" in u or "/posts/" in u or "permalink.php" in u),
        None,
    )
    if permalink:
        return permalink
    if profile_id and post_id:
        return f"https://www.facebook.com/permalink.php?story_fbid={post_id}&id={profile_id}"
    return urls[0] if urls else None


def _parse_timeline_edges(response_text: str) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for line in response_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        data = payload.get("data") or {}
        batch = (
            (data.get("user") or {})
            .get("timeline_list_feed_units", {})
            .get("edges")
        )
        if isinstance(batch, list):
            edges.extend(batch)
            continue
        if isinstance(data, dict) and isinstance(data.get("node"), dict) and "cursor" in data:
            edges.append(data)
    return edges


def _list_from_timeline(base: str, html: str, *, limit: int) -> dict[str, Any] | None:
    """Primary path: ProfileCometTimelineFeedQuery (posts + reels on the wall)."""
    pre = _timeline_preloader(html)
    if not pre:
        return None
    query_id, variables = pre
    profile_id = (
        str(variables.get("userID") or "")
        or _profile_id_from_url(base)
        or _profile_id_from_url(html[:2000])
    )
    if not profile_id:
        return None

    variables = dict(variables)
    variables["userID"] = profile_id
    variables["count"] = max(int(limit), 1)
    variables["stream_count"] = max(int(limit), 1)

    lsd = _lsd_token(html)
    if not lsd:
        return None

    profile = fb_config.BROWSER_PROFILES[0]
    session = fb_http._get_session(profile["client_identifier"])
    headers = {
        **profile["headers"],
        "Content-Type": "application/x-www-form-urlencoded",
        "X-FB-Friendly-Name": "ProfileCometTimelineFeedQuery",
        "X-FB-LSD": lsd,
        "Origin": "https://www.facebook.com",
        "Referer": base,
    }
    body = {
        "av": "0",
        "__user": "0",
        "__a": "1",
        "lsd": lsd,
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "ProfileCometTimelineFeedQuery",
        "variables": json.dumps(variables, separators=(",", ":")),
        "server_timestamps": "true",
        "doc_id": query_id,
    }
    try:
        resp = session.post(
            "https://www.facebook.com/api/graphql/",
            headers=headers,
            data=urlencode(body),
            timeout_seconds=fb_config.DEFAULT_TIMEOUT,
        )
        text = resp.text or ""
    except Exception:  # noqa: BLE001
        return None
    if not text or text.lstrip().startswith('{"errors"'):
        # still may contain data; only bail if empty
        if '"timeline_list_feed_units"' not in text:
            return None

    display_name = None
    m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html, re.I)
    if m:
        display_name = m.group(1).split(" | ")[0].strip() or m.group(1)

    posts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for edge in _parse_timeline_edges(text):
        node = edge.get("node") or {}
        post_id = str(node.get("post_id") or "") or None
        if not post_id or post_id in seen:
            continue
        seen.add(post_id)
        urls = _walk_urls(node)
        url = _best_post_url(urls, profile_id=profile_id, post_id=post_id)
        kind = "reel" if url and "/reel/" in url else "post"
        posts.append({
            "platform": "facebook",
            "url": url,
            "id": post_id,
            "username": display_name or profile_id,
            "display_name": display_name,
            "caption": _walk_caption(node),
            "likes": None,
            "comments": None,
            "reposts": None,
            "shares": None,
            "bookmarks": None,
            "views": None,
            "post_date": iso_from_timestamp(node.get("creation_time")),
            "status": "ok",
            "kind": kind,
        })
        if len(posts) >= limit:
            break

    if not posts:
        return None

    followers = None
    try:
        followers = profile_followers(base)
    except Exception:  # noqa: BLE001
        followers = None

    return {
        "platform": "facebook",
        "username": display_name or profile_id,
        "display_name": display_name,
        "followers": followers,
        "profile_url": base,
        "posts": posts[:limit],
        "count": min(len(posts), limit),
        "source": "facebook_timeline_graphql",
        "note": "Timeline feed (posts + reels). Use enrich=True for likes/comments/shares.",
    }


def _profile_tabs(base: str) -> list[str]:
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


def _list_from_tabs(base: str, *, limit: int) -> dict[str, Any]:
    """Fallback: scrape media ids from profile / reels tabs."""
    profile_id = _profile_id_from_url(base)
    tabs = _profile_tabs(base)
    video_ids: list[str] = []
    post_ids: list[str] = []
    display_name = None

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

    followers = None
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
        "note": "Fallback tab scrape (reels-heavy). Timeline GraphQL unavailable.",
    }


def list_profile_posts(profile_url: str, *, limit: int = 20) -> dict[str, Any]:
    """List recent public timeline posts (including reels) for a Facebook profile/page."""
    base = _base_profile(profile_url)
    html = ""
    try:
        html = fetch_html(base) or ""
    except Exception:  # noqa: BLE001
        html = ""

    if html:
        timeline = _list_from_timeline(base, html, limit=limit)
        if timeline and timeline.get("posts"):
            return timeline

    return _list_from_tabs(base, limit=limit)
