"""Fetching pages with a browser-like TLS fingerprint.

Settings come from :mod:`.config` at call time, not import time, so
``fb.config.DEFAULT_TIMEOUT = 60`` takes effect on the very next request.

Proxies are per call and follow ``requests`` semantics: pass a
``{"http": ..., "https": ...}`` mapping, or a single URL string to use for both
schemes. Pass nothing and the request goes out direct.

The TLS fingerprint and the request headers always come from the same profile,
so the handshake never contradicts what the headers claim.
"""

from __future__ import annotations

import logging
import random
import threading

import tls_client
from tls_client.config import TLSClientConfig

from . import config

log = logging.getLogger(__name__)

__all__ = ["fetch_html", "normalise_proxy"]


def normalise_proxy(proxy):
    """Coerce ``proxy`` into the mapping tls_client wants, ``requests`` style.

    ``None`` / ``{}`` / ``""``            -> ``None``  (connect directly)
    ``{"http": ..., "https": ...}``       -> passed straight through
    ``"http://user:pass@host:port"``      -> used for both schemes
    ``"host:port"``                       -> ``http://`` added, then as above

    A scheme-less string is assumed to be HTTP, which is what a proxy without
    one almost always is. Anything else -- SOCKS in particular -- keeps the
    scheme it was given.
    """
    if not proxy:
        return None
    if isinstance(proxy, dict):
        return proxy or None
    if not isinstance(proxy, str):
        raise TypeError(f"proxy must be a str or dict, got {type(proxy).__name__}")

    url = proxy.strip()
    if not url:
        return None
    if "://" not in url:
        url = f"http://{url}"
    return {"http": url, "https": url}


# tls_client sessions are expensive to build and are not thread-safe, so keep one
# session per (thread, fingerprint) and reuse it.
_sessions = threading.local()


def _get_session(client_identifier):
    pool = getattr(_sessions, "pool", None)
    if pool is None:
        pool = _sessions.pool = {}
    session = pool.get(client_identifier)
    if session is None:
        session = tls_client.Session(
            config=TLSClientConfig(
                client_identifier=client_identifier,
                random_tls_extension_order=True,
            )
        )
        pool[client_identifier] = session
    return session


def _pick_profile():
    profiles = config.BROWSER_PROFILES
    if not profiles:
        raise RuntimeError("config.BROWSER_PROFILES is empty")
    return random.choice(profiles)


def fetch_html(url, timeout=None, retries=None, proxy=None, headers=None,
               profile=None):
    """GET ``url`` with a browser-like TLS fingerprint.

    Args:
        url: the page to fetch.
        timeout: seconds per attempt. Defaults to :data:`config.DEFAULT_TIMEOUT`.
        retries: attempts before giving up. Defaults to
            :data:`config.DEFAULT_RETRIES`.
        proxy: a ``{"http": ..., "https": ...}`` mapping, or a single URL
            string used for both schemes. Omit it to connect directly.
        headers: extra headers merged over the chosen profile's own.
        profile: force one entry of :data:`config.BROWSER_PROFILES` instead of
            rotating -- useful for reproducing a specific fingerprint.

    Returns the response body, or ``None`` if every attempt failed.
    """
    if not url:
        return None

    timeout = config.DEFAULT_TIMEOUT if timeout is None else timeout
    retries = config.DEFAULT_RETRIES if retries is None else retries
    proxies = normalise_proxy(proxy)

    last_error = None
    for attempt in range(1, max(1, retries) + 1):
        # Re-picked per attempt, so a retry gets a fresh fingerprint and proxy.
        chosen = profile or _pick_profile()
        identifier = chosen["client_identifier"]
        try:
            response = _get_session(identifier).get(
                url,
                headers=config.profile_headers(chosen, headers),
                proxies=proxies,
                timeout=timeout,
            )
        except Exception as exc:  # network / TLS layer
            last_error = exc
            log.warning("fetch failed (%s/%s, %s) for %s: %s",
                        attempt, retries, identifier, url, exc)
            continue

        if response.status_code == 200:
            return response.text

        last_error = f"HTTP {response.status_code}"
        log.warning("fetch returned %s (%s/%s, %s) for %s",
                    response.status_code, attempt, retries, identifier, url)

    log.error("giving up on %s: %s", url, last_error)
    return None
