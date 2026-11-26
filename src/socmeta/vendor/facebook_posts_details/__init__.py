"""Extract public data from Facebook post, reel, video, photo and profile URLs.

Facebook server-renders each page with the data it needs embedded in
``<script type="application/json">`` blocks, and publishes a summary in the
document's Open Graph tags. This library reads both. It does not log in and does
not touch private content -- it only sees what a signed-out browser would.

    import facebook_posts_details as fb

    post = fb.post_data("https://www.facebook.com/reel/941309212326403")
    prof = fb.profile_data("https://www.facebook.com/zuck")

Every returned dict has a fixed set of keys; a field that could not be found is
``None`` (or an empty list/dict) rather than missing, so ``post["likes_count"]``
never raises.
"""

from __future__ import annotations

from . import config
from .errors import (FacebookPostsDetailsError, FetchError, InvalidURL,
                     ParseError)
from .http import fetch_html, normalise_proxy
from .meta import parse_meta_tags
from .payloads import find_key_value, find_parent, iter_graphql_payloads
from .posts import post_data
from .profiles import get_profile_about, profile_about, profile_data
from .urls import (_guess_kind, get_post_id_from_url, get_post_type_from_url,
                   get_profile_id_from_url)

__version__ = "0.1.0"

__all__ = [
    "post_data",
    "profile_data",
    "get_profile_about",
    "profile_about",
    "scrape",
    "fetch_html",
    "normalise_proxy",
    "iter_graphql_payloads",
    "parse_meta_tags",
    "get_profile_id_from_url",
    "get_post_id_from_url",
    "get_post_type_from_url",
    "find_key_value",
    "find_parent",
    "config",
    "FacebookPostsDetailsError",
    "InvalidURL",
    "FetchError",
    "ParseError",
    "__version__",
]


def scrape(url, kind="auto", with_profile=False, timeout=None, retries=None,
           proxy=None):
    """Scrape ``url``, choosing the right extractor for it.

    Args:
        url: any public Facebook post, reel, video, photo, story or profile URL.
        kind: ``"auto"`` (default) picks from the URL shape; force it with
            ``"post"``, ``"profile"`` or ``"about"``.
        with_profile: for posts, also scrape the author's profile into the
            ``"user"`` key. Costs one extra request.
        timeout: per-request timeout in seconds. Defaults to
            :data:`config.DEFAULT_TIMEOUT`.
        retries: attempts per request. Defaults to :data:`config.DEFAULT_RETRIES`.
        proxy: ``"host:port"``, ``"user:pass@host:port"``, a full proxy URL or a
            ``{"http": ..., "https": ...}`` mapping, used for this call only.

    Returns the scraped dict, or ``None`` when the page could not be read.

    Raises:
        InvalidURL: if ``kind`` is not one of auto/post/profile/about.
    """
    kwargs = {"timeout": timeout, "retries": retries, "proxy": proxy}

    if kind == "auto":
        kind = _guess_kind(url)
    if kind == "post":
        return post_data(url, with_profile=with_profile, **kwargs)
    if kind == "profile":
        return profile_data(url, **kwargs)
    if kind == "about":
        return profile_about(url, **kwargs)
    raise InvalidURL(f"unknown kind {kind!r}; expected auto/post/profile/about",
                     url=url, kind=kind)
