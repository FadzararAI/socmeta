"""Reading the GraphQL payloads Facebook embeds in the page.

Every page ships its data inside ``<script type="application/json"
data-content-len="...">`` blocks. Each block is ``{"require": [...]}`` and each
GraphQL response sits at ``__bbox.result``::

    {"data": {...}, "extensions": {...}, "label": ..., "path": [...]}
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

__all__ = ["iter_graphql_payloads", "find_key_value", "find_parent"]

_SCRIPT_OPEN = "<script"


_SCRIPT_CLOSE = "</script>"


_CONTENT_LEN_ATTR = "data-content-len"


#: GraphQL payload path roots that describe *other* content preloaded onto the
#: page (the reels queued behind this one) rather than the requested URL.
_FOREIGN_PAYLOAD_ROOTS = frozenset({"viewer"})


def find_key_value(data, target_key):
    """Depth-first search for ``target_key``; return its value or ``None``."""
    if isinstance(data, dict):
        if target_key in data:
            return data[target_key]
        for value in data.values():
            result = find_key_value(value, target_key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_key_value(item, target_key)
            if result is not None:
                return result
    return None


def find_parent(data, target_key, target_value):
    """Return the first dict where ``data[target_key] == target_value``.

    Depth-first, pre-order, and it stops at the first hit -- the previous
    implementation walked the whole tree collecting every match even though
    callers only ever used the first one.
    """
    if isinstance(data, dict):
        if target_key in data and data[target_key] == target_value:
            return data
        for value in data.values():
            found = find_parent(value, target_key, target_value)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_parent(item, target_key, target_value)
            if found is not None:
                return found
    return None


def _dig(data, *keys, default=None):
    """``data[k1][k2]...`` that returns ``default`` instead of raising."""
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key)
        if data is None:
            return default
    return data


def _iter_script_blocks(html):
    """Yield the body of every ``<script type="application/json" data-content-len=...>``.

    A regex for this backtracks badly -- ``[^>]*`` is retried for every ``<script``
    on a multi-megabyte page, which measured as ~60% of total runtime. Anchoring
    the scan on the rare ``data-content-len`` attribute and walking outward with
    ``str.find`` produces the identical block list 12-20x faster.
    """
    pos = 0
    while True:
        marker = html.find(_CONTENT_LEN_ATTR, pos)
        if marker == -1:
            return

        start = html.rfind(_SCRIPT_OPEN, 0, marker)
        if start == -1:
            pos = marker + len(_CONTENT_LEN_ATTR)
            continue

        tag_end = html.find(">", start)
        if tag_end == -1:
            return
        if not start < marker < tag_end:
            # The attribute name appears inside a script body, not in a tag.
            pos = marker + len(_CONTENT_LEN_ATTR)
            continue

        end = html.find(_SCRIPT_CLOSE, tag_end + 1)
        if end == -1:
            return
        pos = end + len(_SCRIPT_CLOSE)

        attrs = html[start + len(_SCRIPT_OPEN):tag_end]
        if attrs[:1].isspace() and "application/json" in attrs:
            yield html[tag_end + 1:end]


def _loads(raw):
    """Parse a block, returning ``None`` instead of raising on malformed JSON."""
    try:
        return json.loads(raw.strip())
    except (ValueError, TypeError) as exc:
        log.debug("skipping malformed JSON block: %s", exc)
        return None


def _iter_payloads(node):
    """Yield every ``__bbox.result`` GraphQL envelope under ``node``, in document order."""
    if isinstance(node, dict):
        bbox = node.get("__bbox")
        if isinstance(bbox, dict):
            result = bbox.get("result")
            if isinstance(result, dict) and "data" in result:
                yield result
        for value in node.values():
            yield from _iter_payloads(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_payloads(item)


def iter_graphql_payloads(html):
    """Yield every GraphQL response Facebook embedded in ``html``.

    Each item is the envelope Facebook streams inside ``__bbox.result``::

        {"data": {...}, "extensions": {...}, "label": ..., "path": [...]}

    ``label`` names the Relay fragment that produced the chunk -- e.g.
    ``FBReelsMediaFooter_footer``, ``ProfileCometEntityConvergenceHeader_
    profileHeaderRenderer``, ``CometFullUFIRendererExperimental_story`` -- which
    is a far more stable selector than grepping the raw text for a renderer name.
    Use this to reach fields this module does not extract.
    """
    for raw in _iter_script_blocks(html):
        block = _loads(raw)
        if block is not None:
            yield from _iter_payloads(block)


def _payload_data(block):
    """The GraphQL ``data`` root of a parsed block.

    Every payload-carrying block observed so far holds exactly one payload, so
    this normally agrees with a plain search for a ``"data"`` key -- but it says
    so deliberately instead of trusting whichever ``data`` a blind walk hits
    first. Falls back to the blind search for blocks with no ``__bbox`` envelope.
    """
    for payload in _iter_payloads(block):
        data = payload.get("data")
        if data is not None:
            return data
    return find_key_value(block, "data")


def _payload_is_ours(payload):
    """False when a chunk describes a neighbouring feed item, not the requested URL.

    A ``/reel/`` page preloads the next few reels in the viewer's feed, each
    arriving as its own payload rooted at ``["viewer", "lasso_blue_feed", ...]``
    complete with its own like and comment counts.
    """
    path = payload.get("path") or []
    return not path or path[0] not in _FOREIGN_PAYLOAD_ROOTS


def _iter_json_blocks(html, markers):
    """Yield ``(raw_block, parsed_json)`` for blocks containing one of ``markers``."""
    for raw in _iter_script_blocks(html):
        if not any(marker in raw for marker in markers):
            continue
        data = _loads(raw)
        if data is not None:
            yield raw, data
