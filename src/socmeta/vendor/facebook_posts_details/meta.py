"""Reading the Open Graph / meta tags in the document head.

A second, independent view of the same page -- the data link previews use. It
survives GraphQL schema churn, so it backstops anything the payload walk missed.
Both of its values are lossy (rounded counts, truncated text), so it only ever
fills gaps and never overrides a payload value.
"""

from __future__ import annotations

import re
from html import unescape

from .normalize import _COUNT_MULTIPLIER, _image

__all__ = ["parse_meta_tags"]

#: ``<meta property|name="..." content="...">`` in any attribute order.
_META_RE = re.compile(
    r'<meta\s+(?=[^>]*?\b(?:property|name)\s*=\s*"([^"]+)")'
    r'(?=[^>]*?\bcontent\s*=\s*"([^"]*)")[^>]*>',
    re.IGNORECASE,
)


#: "104K reactions", "9.4M views", "1K shares" inside an og:title.
_OG_STAT_RE = re.compile(
    r"([\d][\d.,]*)\s*([KMB])?\s+(views?|reactions?|shares?|comments?)", re.IGNORECASE)


_FB_PROFILE_ID_RE = re.compile(r"fb://profile/(\d+)")


#: Leading "Name. 63,803 likes · 46,821 talking about this. " in an og:description.
_OG_DESC_STATS_RE = re.compile(
    r"^.*?\b[\d,]+ likes(?: · [\d,]+ [^.·]*)*\.\s*", re.IGNORECASE)


#: How far to scan for the document head when ``</head>`` is missing.
_HEAD_SCAN_LIMIT = 500_000


def parse_meta_tags(html):
    """Return every ``<meta property|name=... content=...>`` from the document head.

    Facebook publishes a compact summary of the page here, and it is far more
    stable than the GraphQL payloads -- it is the same data link previews use.
    Notably:

    ``og:description``  the post text, or "Name. N likes · ... " on a profile
    ``og:title``        rounded engagement on reels/videos:
                        ``"104K reactions · 1K shares | <text> | <author>"``
    ``al:ios:url``      ``fb://profile/<numeric id>`` on profile pages
    ``og:image``        the post image / profile picture

    Values are HTML-unescaped. First occurrence of a key wins.
    """
    if not html:
        return {}
    end = html.find("</head>")
    head = html[:end + 7] if 0 <= end <= _HEAD_SCAN_LIMIT else html[:_HEAD_SCAN_LIMIT]

    tags = {}
    for key, content in _META_RE.findall(head):
        tags.setdefault(unescape(key), unescape(content))
    return tags


def _og_title_stats(title):
    """``"104K reactions · 1K shares | ..."`` -> ``{"reactions": 104000, "shares": 1000}``.

    Only the segment before the first ``|`` is read -- everything after it is
    the caption and the author name, which can contain digits of their own.
    """
    if not title:
        return {}
    stats = {}
    for number, suffix, kind in _OG_STAT_RE.findall(title.split("|", 1)[0]):
        try:
            value = float(number.replace(",", ""))
        except ValueError:
            continue
        stats[kind.lower().rstrip("s") + "s"] = int(
            value * _COUNT_MULTIPLIER[(suffix or "").upper()]
        )
    return stats


def _og_title_author(title):
    """The author name an og:title ends with, or the whole title when it is a name."""
    if not title:
        return None
    parts = [part.strip() for part in title.split("|")]
    if len(parts) == 1:
        # A bare name ("Zee Business"); guard against a lone stats string.
        return parts[0] if parts[0] and not _OG_STAT_RE.search(parts[0]) else None
    return parts[-1] or None


def _og_description_bio(description):
    """Strip the ``"Name. 63,803 likes · 46,821 talking about this. "`` preamble."""
    if not description:
        return None
    return _OG_DESC_STATS_RE.sub("", description, count=1).strip() or None


def _apply_post_meta(result, meta):
    """Fill anything the payload walk missed from the page's meta tags.

    Strictly a fallback, because both sources here are lossy:

    * the counts in ``og:title`` are rounded for display ("104K reactions"),
      while the payloads carry the exact figure (104320);
    * ``og:description`` is cut to roughly 200 characters with a trailing
      ellipsis, so it can be a small fraction of a long post.

    An exact value already recovered from the payloads therefore always wins,
    and the ellipsis is left in place so truncated text is visibly truncated
    rather than passing for the whole post.
    """
    if not result["post_text"]:
        result["post_text"] = meta.get("og:description") or meta.get("description")

    if not result["name"]:
        result["name"] = _og_title_author(meta.get("og:title"))

    stats = _og_title_stats(meta.get("og:title"))
    for field, kind in (("views_count", "views"), ("likes_count", "reactions"),
                        ("share_count", "shares"), ("comments_count", "comments")):
        if result[field] is None and kind in stats:
            result[field] = stats[kind]

    if not result["post_images"] and meta.get("og:image"):
        # og:image:alt repeats the title/author rather than describing the image,
        # so it is not a caption.
        result["post_images"].append(_image(meta["og:image"]))


def _apply_profile_meta(result, meta):
    """Same idea for profiles -- fill only what the payload walk left empty."""
    if not result["name"]:
        result["name"] = meta.get("og:title")

    if not result["profile_id_number"]:
        for key in ("al:ios:url", "al:android:url"):
            match = _FB_PROFILE_ID_RE.search(meta.get(key) or "")
            if match:
                result["profile_id_number"] = match.group(1)
                break

    if not result["profile_pic"]:
        result["profile_pic"] = meta.get("og:image")

    if not result["bio"]:
        result["bio"] = _og_description_bio(meta.get("og:description"))
