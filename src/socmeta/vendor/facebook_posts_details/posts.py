"""Scraping a post, reel, video, photo or story."""

from __future__ import annotations

import logging

from .http import fetch_html
from .meta import _apply_post_meta, parse_meta_tags
from .normalize import _image, _parse_count, _to_int, _to_iso
from .payloads import (_dig, _iter_payloads, _iter_script_blocks, _loads,
                       _payload_data, _payload_is_ours, find_key_value, find_parent)
from .profiles import profile_data
from .urls import get_post_id_from_url, get_post_type_from_url

log = logging.getLogger(__name__)

__all__ = ["post_data"]

def _post_block_wanted(raw, result):
    """Would any branch still learn something from this block?

    ``creation_time`` and ``transcript`` appear in most blocks on a page, so
    parsing every one of them dominates the runtime. The two cheap branches only
    ever fill in *missing* fields, so once those fields are known the parse is
    provably a no-op and can be skipped.
    """
    if ("CometStorySections" in raw
            or "UFI2ViewCountRenderer" in raw
            or "first_frame_thumbnail" in raw
            or "RelayPrefetchedStreamCache" in raw
            or "currMedia" in raw
            or "transcript" in raw):
        return True
    if "all_video_dash_prefetch_representations" in raw and not result["video_url"]:
        return True
    if "creation_time" in raw and not (
        result["publish_date"] and result["name"]
        and result["profile_url"] and result["profile_image"]
    ):
        return True
    return False


def _empty_post(url):
    return {
        "url": url,
        "post_id": get_post_id_from_url(url),
        "post_type": get_post_type_from_url(url),
        "post_text": None,
        "publish_date": None,
        "publish_date_iso": None,
        "likes_count": None,
        "comments_count": None,
        "share_count": None,
        "views_count": None,
        "post_images": [],
        "video_url": None,
        "transcript": None,
        "name": None,
        "profile_url": None,
        "profile_image": None,
        # Populated only when post_data(..., with_profile=True); otherwise {}.
        "user": {},
    }


def _extract_story(result, data):
    """Regular feed post: text, author, counts and attached images."""
    story_sections = find_parent(data, "__typename", "CometStorySections")
    if story_sections is None:
        return False

    story = _dig(story_sections, "content", "story", default={})
    actors = story.get("actors") or []
    actor = actors[0] if actors else {}

    result["post_text"] = _dig(story, "message", "text")
    result["name"] = actor.get("name")
    result["profile_url"] = actor.get("url")
    result["profile_image"] = _dig(actor, "profile_picture", "uri")
    result["publish_date"] = _to_int(
        _dig(story_sections, "timestamp", "story", "creation_time")
    )

    _extract_story_images(result, data, story)

    feedback_node = find_parent(
        story_sections, "__typename", "UnauthenticatedUCometUFISummaryAndActionsRenderer"
    )
    if feedback_node is not None:
        feedback = feedback_node.get("feedback") or {}
        result["likes_count"] = _to_int(_dig(feedback, "reaction_count", "count"))
        result["comments_count"] = _to_int(
            _dig(feedback, "comment_rendering_instance", "comments", "total_count")
            or _dig(feedback, "comments_count_summary_renderer", "feedback",
                    "comment_rendering_instance", "comments", "total_count")
        )
        result["share_count"] = _to_int(_dig(feedback, "share_count", "count"))
    return True


def _extract_story_images(result, data, story):
    attachments = story.get("attachments") or []
    first = attachments[0] if attachments else {}
    subattachments = _dig(first, "styles", "attachment", "all_subattachments")

    if subattachments:
        for node in subattachments.get("nodes") or []:
            media = node.get("media") or {}
            uri = _dig(media, "viewer_image", "uri")
            if uri:
                result["post_images"].append(
                    _image(uri, media.get("accessibility_caption"))
                )
        return

    # Single-photo posts keep the image somewhere else in the payload.
    for attachment_group in find_key_value(data, "attachments") or []:
        attachment = find_key_value(attachment_group, "attachment")
        if not isinstance(attachment, dict):
            continue
        media = attachment.get("media") or {}
        uri = _dig(media, "photo_image", "uri")
        if uri:
            result["post_images"].append(
                _image(uri, media.get("accessibility_caption"))
            )


def _merge_feedback(result, feedback):
    """Fill in engagement counts that are still unknown."""
    if result["likes_count"] is None:
        result["likes_count"] = _to_int(_dig(feedback, "reaction_count", "count"))
    if result["comments_count"] is None:
        result["comments_count"] = _to_int(
            _dig(feedback, "comment_rendering_instance", "comments", "total_count")
            or _dig(feedback, "comments_count_summary_renderer", "feedback",
                    "comment_rendering_instance", "comments", "total_count")
        )
    if result["share_count"] is None:
        result["share_count"] = _to_int(_dig(feedback, "share_count", "count"))


def _merge_photo_media(result, media):
    if not result["post_text"]:
        result["post_text"] = _dig(media, "message", "text")

    uri = _dig(media, "image", "uri")
    if uri and not any(img["url"] == uri for img in result["post_images"]):
        result["post_images"].append(_image(uri, media.get("accessibility_caption")))

    story = media.get("creation_story") or media.get("container_story") or {}
    actors = story.get("actors") or []
    if actors and not result["name"]:
        result["name"] = actors[0].get("name")


def _extract_photo(result, data):
    """Photo-viewer pages (``/photo/?fbid=...``).

    These carry no ``CometStorySections`` tree. The image, its caption, the
    message and the feedback arrive as separate deferred chunks all rooted at
    ``currMedia``, so merge whatever each chunk happens to carry.

    Returns the media's own ``created_time``. That is the *photo's* timestamp,
    which can differ by a second or two from the enclosing post's -- so the
    caller keeps it only as a fallback for when the post has no ``creation_time``.
    """
    created_time = None
    for payload in _iter_payloads(data):
        chunk = payload.get("data")
        if not isinstance(chunk, dict):
            continue

        media = chunk.get("currMedia")
        if not isinstance(media, dict) and (payload.get("path") or [])[:1] == ["currMedia"]:
            media = chunk
        if isinstance(media, dict):
            _merge_photo_media(result, media)
            created_time = created_time or _to_int(media.get("created_time"))

        renderer = find_parent(
            chunk, "__typename", "UnauthenticatedUCometUFISummaryAndActionsRenderer"
        )
        if renderer is not None:
            _merge_feedback(result, renderer.get("feedback") or {})

    return created_time


def _extract_view_counts(result, data):
    """Video/reel play counts plus the counts that ship alongside them.

    Returns ``False`` when this block only *mentions* the renderer without
    containing it -- such decoy blocks carry no counts, and letting them through
    would overwrite good values with ``None``.
    """
    view_node = find_parent(data, "__typename", "UFI2ViewCountRenderer")
    if view_node is None:
        return False

    result["views_count"] = _to_int(_dig(view_node, "feedback", "play_count"))

    main = _payload_data(data)
    if isinstance(main, dict):
        result["comments_count"] = _to_int(
            _dig(main, "feedback", "comment_rendering_instance", "comments", "total_count")
        )
        result["likes_count"] = _to_int(_dig(main, "feedback", "reaction_count", "count"))
        result["post_text"] = _dig(main, "creation_story", "message", "text")

    _extract_video_url(result, data)
    return True


def _video_url_from_extensions(extensions):
    if not isinstance(extensions, dict):
        return None
    representations = extensions.get("all_video_dash_prefetch_representations") or []
    if not representations:
        return None
    reps = representations[0].get("representations") or []
    return reps[0].get("base_url") if reps else None


def _extract_video_url(result, data):
    """Pull the progressive/DASH URL out of a block's GraphQL extensions.

    Checks every payload rather than only the first ``extensions`` a blind walk
    finds -- when a block streams several chunks, the video representations are
    not necessarily in the first one.
    """
    for payload in _iter_payloads(data):
        url = _video_url_from_extensions(payload.get("extensions"))
        if url:
            result["video_url"] = url
            return

    url = _video_url_from_extensions(find_key_value(data, "extensions"))
    if url:
        result["video_url"] = url


def _extract_reel_owner(result, data):
    video = _dig(_payload_data(data) or {}, "video", default={})
    creation_story = video.get("creation_story") or {}
    owner = _dig(creation_story, "short_form_video_context", "video_owner", default={})

    result["post_text"] = _dig(creation_story, "message", "text")
    result["name"] = result["name"] or owner.get("name")
    result["profile_url"] = owner.get("url")
    result["profile_image"] = _dig(owner, "displayPicture", "uri")


def _extract_reel_feedback(result, data):
    """Reel counts, which ride along in the prefetched stream cache.

    Selecting the right chunk matters: the counts for this reel and for the
    reels queued behind it sit in sibling payloads. The old ``"==" in id`` test
    did not separate them -- that was just base64 padding, present on some reels
    and not others -- so a reel with 104K likes reported nothing at all.
    The payload path identifies the subject exactly.

    Only the *reduced* share count is published on reels ("1K", "1.4K"), so
    ``share_count`` is rounded the same way the page displays it.
    """
    for payload in _iter_payloads(data):
        if not _payload_is_ours(payload):
            continue
        node = payload.get("data")
        if not isinstance(node, dict):
            continue

        feedback = node.get("feedback") or {}

        if result["comments_count"] is None:
            result["comments_count"] = _to_int(feedback.get("total_comment_count"))
        if result["share_count"] is None:
            result["share_count"] = _parse_count(feedback.get("share_count_reduced"))
        if result["likes_count"] is None:
            result["likes_count"] = _to_int(
                _dig(node, "fb_reel_react_button", "story", "feedback", "likers", "count")
                or _dig(feedback, "likers", "count")
            )


def post_data(url, with_profile=False, timeout=None, retries=None, proxy=None):
    """Scrape a public post, reel, video, photo or story.

    Args:
        url: the post / reel / video / photo / story URL.
        with_profile: also scrape the author's profile and return it under the
            ``"user"`` key. This costs a second request. When ``False`` (the
            default) ``"user"`` is an empty dict, so the key is always present.

    Returns a dict with a fixed key set (see module docstring), or ``None`` when
    the page could not be fetched or held no recognisable post.
    """
    if not url:
        log.error("post_data() needs a url")
        return None

    html = fetch_html(url, timeout=timeout, retries=retries, proxy=proxy)
    if not html:
        return None

    result = _empty_post(url)
    photo_created_time = None

    def finish():
        if not result["publish_date"]:
            result["publish_date"] = photo_created_time
        result["publish_date_iso"] = _to_iso(result["publish_date"])
        if with_profile and result["profile_url"]:
            result["user"] = profile_data(
                result["profile_url"], timeout=timeout, retries=retries, proxy=proxy
            ) or {}
        return result

    for raw in _iter_script_blocks(html):
        if not _post_block_wanted(raw, result):
            continue
        data = _loads(raw)
        if data is None:
            continue

        if "CometStorySections" in raw:
            try:
                if _extract_story(result, data):
                    return finish()
            except Exception:  # one malformed block must not kill the scrape
                log.exception("failed to parse CometStorySections block")
            continue

        if "UFI2ViewCountRenderer" in raw:
            try:
                if not _extract_view_counts(result, data):
                    continue
            except Exception:
                log.exception("failed to parse UFI2ViewCountRenderer block")
                continue

        if "currMedia" in raw:
            # Must run for every chunk -- image, message and feedback arrive
            # separately -- so call it before combining, never short-circuited.
            created_time = _extract_photo(result, data)
            photo_created_time = photo_created_time or created_time

        if "first_frame_thumbnail" in raw:
            _extract_reel_owner(result, data)

        if "RelayPrefetchedStreamCache" in raw:
            _extract_reel_feedback(result, data)

        if "all_video_dash_prefetch_representations" in raw and not result["video_url"]:
            _extract_video_url(result, data)

        if "creation_time" in raw:
            result["publish_date"] = result["publish_date"] or _to_int(
                find_key_value(data, "creation_time")
            )
            result["name"] = result["name"] or find_key_value(data, "name")
            result["profile_url"] = result["profile_url"] or find_key_value(data, "profile_url")
            if not result["profile_image"]:
                picture = find_key_value(data, "profile_picture")
                if isinstance(picture, dict):
                    result["profile_image"] = picture.get("uri")

        if "transcript" in raw:
            transcript = find_key_value(data, "transcript")
            if transcript:
                result["transcript"] = transcript

    # Meta tags are an independent, far more stable view of the same page.
    # They only fill gaps -- see _apply_post_meta.
    _apply_post_meta(result, parse_meta_tags(html))

    if any((result["post_text"], result["name"], result["video_url"], result["post_images"])):
        return finish()

    log.warning("no post data found in %s", url)
    return None
