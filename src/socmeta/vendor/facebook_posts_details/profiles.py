"""Scraping a profile or page, and its About tabs."""

from __future__ import annotations

import logging

from .http import fetch_html
from .meta import _apply_profile_meta, parse_meta_tags
from .normalize import _about_entry, _add_about, _parse_count
from .payloads import (_dig, _iter_json_blocks, _payload_data,
                       find_key_value, find_parent)
from .urls import get_profile_id_from_url

log = logging.getLogger(__name__)

__all__ = ["profile_data", "get_profile_about", "profile_about"]

#: Only blocks containing one of these markers are worth parsing as JSON.
#: (Posts use :func:`_post_block_wanted` instead, which is state-aware.)
_PROFILE_MARKERS = (
    "category_name",
    "profile_tile_section_type",
    "XFBProfileEntityConvergenceHeaderRenderer",
)


#: UI placeholders that show up as "About" values but carry no information.
_SKIP_ABOUT_VALUES = frozenset({"Admin info", "See All", "See all"})


def _empty_profile(url):
    return {
        "url": url,
        "profile_id": get_profile_id_from_url(url),
        "profile_id_number": None,
        "name": None,
        "bio": None,
        "category_name": None,
        "gender": None,
        "is_verified": False,
        "followers": None,
        "followers_text": None,
        "following": None,
        "following_text": None,
        "profile_pic": None,
        "cover_photo": None,
        "about_section": {},
        "photos": [],
    }


def _extract_profile_header(result, data):
    """Name, counts, avatar and cover from the profile header renderer."""
    user = find_parent(data, "__isProfile", "User")
    if user is None:
        return

    social = _dig(user, "profile_social_context", "content") or []
    if len(social) >= 1:
        result["followers_text"] = _dig(social[0], "text", "text")
    if len(social) >= 2:
        result["following_text"] = _dig(social[1], "text", "text")
    result["followers"] = _parse_count(result["followers_text"])
    result["following"] = _parse_count(result["following_text"])

    result["cover_photo"] = _dig(user, "cover_photo", "photo", "image", "uri")
    result["name"] = user.get("name")
    result["profile_id_number"] = user.get("id")
    result["is_verified"] = bool(user.get("show_verified_badge_on_profile"))
    result["profile_pic"] = _dig(user, "profilePicLarge", "uri")
    result["gender"] = user.get("gender")

    bio = _dig(user, "header_top_row", "profile_user", "profile_status",
               "profile_status_text", "text")
    if bio:
        result["bio"] = bio


def _extract_profile_tiles(result, data):
    """The Intro / Work / Education / Photos tiles below the header."""
    sections = find_key_value(data, "profile_tile_sections")
    if not isinstance(sections, dict):
        return

    for section in sections.get("edges") or []:
        node = section.get("node") or {}
        section_type = node.get("profile_tile_section_type")
        if not section_type:
            continue

        if section_type == "PHOTOS":
            tile_items = find_key_value(section, "profile_tile_items")
            for item in (tile_items or {}).get("nodes") or []:
                uri = _dig(item, "node", "viewer_image", "uri")
                if uri:
                    result["photos"].append(uri)
            continue

        bucket = result["about_section"].setdefault(section_type.lower(), {})
        for view in _dig(node, "profile_tile_views", "nodes") or []:
            for item in find_key_value(view, "nodes") or []:
                _extract_profile_tile_item(bucket, item)


def _extract_profile_tile_item(bucket, item):
    if not isinstance(item, dict):
        return

    # Work / education entries carry their own title + field type.
    if "item_title" in item and "pressable_profile_field_type" in item:
        value = _dig(item, "item_title", "text", "text")
        field_type = (item.get("pressable_profile_field_type") or "").lower()
        if not value or not field_type:
            return
        page_id = item.get("associated_page_id")
        url = f"https://www.facebook.com/{page_id}" if page_id else None
        _add_about(bucket, field_type, _about_entry(value, url))
        return

    tile = _dig(item, "directory_tile_item_renderer", "tile_item", default={})
    value = url = None

    text_obj = _dig(tile, "item_subtitle", "text")
    if isinstance(text_obj, dict):
        value = text_obj.get("text")
        url = _entity_url(text_obj.get("ranges"))

    if not value:
        extra_items = tile.get("extra_text_items") or []
        if extra_items:
            key_obj = extra_items[0].get("key") or {}
            value = key_obj.get("text")
            url = _entity_url(key_obj.get("ranges"))

    if not value:
        return

    key = tile.get("pressable_profile_field_type")
    key = key.lower() if key else value.lower().replace(" ", "_")[:40]
    _add_about(bucket, key, _about_entry(value, url))


def _entity_url(ranges):
    if not ranges:
        return None
    entity = ranges[0].get("entity") or {}
    return entity.get("external_url") or entity.get("url")


def profile_data(url, timeout=None, retries=None, proxy=None):
    """Scrape a public profile or page.

    Returns a dict with a fixed key set, or ``None`` when the page could not be
    fetched or carried no profile.
    """
    if not url:
        log.error("profile_data() needs a url")
        return None

    html = fetch_html(url, timeout=timeout, retries=retries, proxy=proxy)
    if not html:
        return None

    result = _empty_profile(url)

    for raw, data in _iter_json_blocks(html, _PROFILE_MARKERS):
        try:
            if "category_name" in raw:
                result["category_name"] = find_key_value(data, "category_name")
                description = find_key_value(data, "best_description")
                if isinstance(description, dict) and description.get("text"):
                    result["bio"] = description["text"]

            if "profile_tile_section_type" in raw:
                _extract_profile_tiles(result, data)

            if "XFBProfileEntityConvergenceHeaderRenderer" in raw:
                _extract_profile_header(result, data)
        except Exception:
            log.exception("failed to parse a profile block for %s", url)

    # Meta tags fill the gaps, and carry the numeric id verbatim as
    # fb://profile/<id> rather than leaving us to fall back on the vanity name.
    _apply_profile_meta(result, parse_meta_tags(html))

    if not result["name"]:
        log.warning("no profile data found in %s", url)
        return None

    result["profile_id_number"] = result["profile_id_number"] or result["profile_id"]
    return result


def get_profile_about(url, timeout=None, retries=None, proxy=None):
    """Scrape one "About" tab.

    Returns ``(fields, other_sections)`` where ``fields`` maps a field type to a
    list of ``{"value", "url"}`` entries and ``other_sections`` lists the sibling
    About tabs as ``{"name", "id", "url"}``. Always a 2-tuple, never ``None``.
    """
    if not url:
        log.error("get_profile_about() needs a url")
        return {}, []

    html = fetch_html(url, timeout=timeout, retries=retries, proxy=proxy)
    if not html:
        return {}, []

    for raw, data in _iter_json_blocks(html, ("about_app_sections",)):
        try:
            main_section = _payload_data(data)
            collections = find_key_value(main_section, "all_collections")
            other_sections = (collections or {}).get("nodes") or []

            field_sections = find_key_value(main_section, "profile_field_sections")
            if not field_sections:
                continue

            fields = {}
            for section in field_sections:
                for node in _dig(section, "profile_fields", "nodes") or []:
                    field_type = node.get("field_type")
                    if not field_type or field_type == "null_state":
                        continue

                    field = _dig(node, "renderer", "field", default={})
                    value = (
                        _dig(field, "text_content", "text")
                        or _dig(field, "title", "text")
                        or _dig(node, "title", "text")
                    )
                    if not value or value in _SKIP_ABOUT_VALUES:
                        continue

                    _add_about(fields, field_type, _about_entry(value, node.get("link_url")))

            return fields, other_sections
        except Exception:
            log.exception("failed to parse an about block for %s", url)

    return {}, []


def profile_about(url, timeout=None, retries=None, proxy=None):
    """Scrape every "About" sub-tab and merge them into one dict.

    Keys are the tab names slugified, e.g. ``contact_and_basic_info``.
    """
    fields, other_sections = get_profile_about(url, timeout=timeout, retries=retries,
                                               proxy=proxy)
    merged = {"contact_and_basic_info": fields}

    for section in other_sections:
        name = (section.get("name") or "").strip().lower().replace(" ", "_")
        section_url = section.get("url")
        if not name or not section_url or name in merged:
            continue
        section_fields, _ = get_profile_about(section_url, timeout=timeout,
                                             retries=retries, proxy=proxy)
        merged[name] = section_fields

    return merged
