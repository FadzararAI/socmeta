"""Exception hierarchy for :mod:`facebook_posts_details`.

Note what does *not* raise: a page that cannot be fetched, or that holds no
recognisable post, makes ``post_data`` / ``profile_data`` return ``None`` and
log the reason. Scraping a list of URLs is the normal case, and one dead link
should not abort the batch. These exceptions cover programming errors and
explicitly requested strictness instead.
"""
from __future__ import annotations

from typing import Optional

__all__ = [
    "FacebookPostsDetailsError",
    "InvalidURL",
    "FetchError",
    "ParseError",
]


class FacebookPostsDetailsError(Exception):
    """Base class for every error raised by this package."""


class InvalidURL(FacebookPostsDetailsError, ValueError):
    """The URL, or the requested kind of scrape, does not make sense.

    Also a :class:`ValueError`, so code that predates this hierarchy and
    catches ``ValueError`` keeps working.
    """

    def __init__(self, message: str, *, url: Optional[str] = None,
                 kind: Optional[str] = None) -> None:
        super().__init__(message)
        self.url = url
        self.kind = kind


class FetchError(FacebookPostsDetailsError):
    """A page could not be retrieved after every attempt.

    Only raised when strictness is asked for; ``fetch_html`` itself returns
    ``None`` so a batch can carry on past one bad URL.
    """

    def __init__(self, message: str, *, url: Optional[str] = None,
                 status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class ParseError(FacebookPostsDetailsError):
    """A page was fetched but held nothing this library recognises.

    Usually means Facebook changed the payload layout for that page type.
    """

    def __init__(self, message: str, *, url: Optional[str] = None) -> None:
        super().__init__(message)
        self.url = url
