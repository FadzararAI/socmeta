"""Tunable settings, read at call time so changes take effect immediately.

    import facebook_posts_details as fb

    fb.config.DEFAULT_TIMEOUT = 60
    fb.config.EXTRA_HEADERS = {"accept-language": "hi-IN,hi;q=0.9"}
    fb.config.BROWSER_PROFILES = fb.config.desktop_profiles()
"""

from __future__ import annotations

__all__ = [
    "BROWSER_PROFILES",
    "BROWSER_HEADERS",
    "CLIENT_IDENTIFIERS",
    "EXTRA_HEADERS",
    "DEFAULT_TIMEOUT",
    "DEFAULT_RETRIES",
    "chrome_profiles",
    "firefox_profiles",
    "desktop_profiles",
    "safari_profiles",
    "mobile_profiles",
    "profile_headers",
    "VERIFIED_IDENTIFIERS",
    "BROKEN_IDENTIFIERS",
    "THIN_IDENTIFIERS",
]

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 2

#: Merged over the chosen profile's headers on every request. Prefer this over
#: editing a profile, so the TLS fingerprint and its headers stay paired.
EXTRA_HEADERS: dict = {}


# --------------------------------------------------------------------------
# Browser profiles
# --------------------------------------------------------------------------
# A TLS fingerprint is only convincing if the headers agree with it. Announcing
# Chrome 144 in the User-Agent over a Chrome 103 handshake -- or sending the
# Chromium-only `sec-ch-ua` hints over a Firefox handshake -- contradicts the
# fingerprint, so each profile carries the headers that belong with its
# client_identifier and they are always used together.

_ACCEPT_CHROME = ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8")
_ACCEPT_FIREFOX = ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8")
_ACCEPT_SAFARI = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

_COMMON = {
    "accept-language": "en-US,en;q=0.9",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


def _chrome(identifier, version, platform, ua_platform, mobile="?0"):
    """A Chromium profile: User-Agent, Client Hints and Accept all agree."""
    return {
        "client_identifier": identifier,
        "headers": {
            **_COMMON,
            "accept": _ACCEPT_CHROME,
            "sec-ch-ua": (f'"Not(A:Brand";v="99", "Google Chrome";v="{version}", '
                          f'"Chromium";v="{version}"'),
            "sec-ch-ua-mobile": mobile,
            "sec-ch-ua-platform": f'"{ua_platform}"',
            "user-agent": (f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 "
                           f"(KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36"),
        },
    }


def _firefox(identifier, version, platform):
    """A Firefox profile. Firefox sends no sec-ch-ua and a different Accept."""
    return {
        "client_identifier": identifier,
        "headers": {
            **_COMMON,
            "accept": _ACCEPT_FIREFOX,
            "user-agent": (f"Mozilla/5.0 ({platform}; rv:{version}.0) "
                           f"Gecko/20100101 Firefox/{version}.0"),
        },
    }


def _safari(identifier, version, platform):
    """A Safari profile. No sec-ch-ua, WebKit build string."""
    return {
        "client_identifier": identifier,
        "headers": {
            **_COMMON,
            "accept": _ACCEPT_SAFARI,
            "user-agent": (f"Mozilla/5.0 ({platform}) AppleWebKit/605.1.15 "
                           f"(KHTML, like Gecko) Version/{version} Safari/605.1.15"),
        },
    }


# Every identifier below was measured against live Facebook post, reel and
# profile pages (see scripts/benchmark_identifiers.py). 64 of the 65 the library
# offers returned complete data, so Facebook does not appear to gate signed-out
# public pages on the TLS fingerprint -- rotation here is insurance, not a fix.
# Two groups are deliberately left out:
#
#   broken   cloudscraper -- the handshake itself fails
#   thin     chrome_116_PSK, chrome_116_PSK_PQ, firefox_102, firefox_104,
#            firefox_117, nike_android_mobile, mms_ios_3 -- served a smaller
#            page (243 vs 315 JSON blocks). All fields still parsed, but there
#            is less to fall back on, so they are not in the defaults.

# A second measurement, varying the whole profile rather than just the
# fingerprint, found the User-Agent is what actually changes the markup:
#
#   Chrome / Firefox desktop   8/8 fields
#   Safari desktop and iPad    7/8  (no video_url -- Safari is served HLS)
#   Chrome Android, Safari iOS 3/8  (no counts, video_url or publish_date)
#
# That is why the defaults are desktop-only.

#: Fingerprints that returned the richest pages in the benchmark.
VERIFIED_IDENTIFIERS = (
    "chrome_103", "chrome_104", "chrome_105", "chrome_106", "chrome_107",
    "chrome_108", "chrome_109", "chrome_110", "chrome_111", "chrome_112",
    "chrome_117", "chrome_120", "chrome_124", "chrome_131", "chrome_131_PSK",
    "chrome_133", "chrome_133_PSK",
    "safari_15_6_1", "safari_16_0", "safari_ios_15_5", "safari_ios_15_6",
    "safari_ios_17_0", "safari_ios_18_0", "safari_ipad_15_6",
    "firefox_105", "firefox_106", "firefox_108", "firefox_110", "firefox_120",
    "firefox_123", "firefox_132", "firefox_133", "firefox_135",
    "opera_89", "opera_90", "opera_91",
)

#: Known bad: the handshake fails outright.
BROKEN_IDENTIFIERS = ("cloudscraper",)

#: Work, but Facebook serves them a thinner page.
THIN_IDENTIFIERS = (
    "chrome_116_PSK", "chrome_116_PSK_PQ", "firefox_102", "firefox_104",
    "firefox_117", "nike_android_mobile", "mms_ios_3",
)


def chrome_profiles():
    """Modern Chrome desktop profiles. Measured complete (8/8 fields)."""
    return [
        _chrome("chrome_133", "133", "Windows NT 10.0; Win64; x64", "Windows"),
        _chrome("chrome_131", "131", "Windows NT 10.0; Win64; x64", "Windows"),
        _chrome("chrome_131", "131", "Macintosh; Intel Mac OS X 10_15_7", "macOS"),
        _chrome("chrome_124", "124", "X11; Linux x86_64", "Linux"),
        _chrome("chrome_120", "120", "Windows NT 10.0; Win64; x64", "Windows"),
    ]


def firefox_profiles():
    """Firefox desktop profiles. Also complete (8/8 fields)."""
    return [
        _firefox("firefox_135", "135", "Windows NT 10.0; Win64; x64"),
        _firefox("firefox_133", "133", "X11; Linux x86_64"),
        _firefox("firefox_132", "132", "Macintosh; Intel Mac OS X 10.15"),
    ]


def desktop_profiles():
    """Chrome + Firefox desktop -- the widest rotation that loses no data."""
    return chrome_profiles() + firefox_profiles()


def safari_profiles():
    """Safari on macOS and iPad.

    Complete except for ``video_url``: Safari is served HLS rather than the DASH
    prefetch the URL is read from. Fine when you do not need the video file.
    """
    return [
        _safari("safari_16_0", "16.0", "Macintosh; Intel Mac OS X 10_15_7"),
        _safari("safari_15_6_1", "15.6", "Macintosh; Intel Mac OS X 10_15_7"),
        _safari("safari_ipad_15_6", "15.6", "iPad; CPU OS 15_6 like Mac OS X"),
    ]


def mobile_profiles():
    """Phone profiles -- **lossy**, provided only for completeness.

    Facebook serves phone User-Agents a much smaller page: measured at 3 of 8
    fields on a reel, losing ``likes_count``, ``comments_count``,
    ``share_count``, ``video_url`` and ``publish_date``. Prefer
    :func:`desktop_profiles`; reach for these only if you specifically need the
    mobile rendering.
    """
    return [
        _chrome("chrome_133", "133", "Linux; Android 14; Pixel 8", "Android", mobile="?1"),
        _chrome("chrome_131", "131", "Linux; Android 13; SM-S918B", "Android", mobile="?1"),
        _safari("safari_ios_18_0", "18.0", "iPhone; CPU iPhone OS 18_0 like Mac OS X"),
        _safari("safari_ios_17_0", "17.0", "iPhone; CPU iPhone OS 17_0 like Mac OS X"),
    ]


#: Rotated per request. Desktop Chrome by default. Widen the rotation with::
#:
#:     fb.config.BROWSER_PROFILES = fb.config.desktop_profiles()
#:
#: Note that the User-Agent, not the TLS fingerprint, decides which markup
#: Facebook serves -- see the measurements above mobile_profiles().
BROWSER_PROFILES = desktop_profiles()

#: The TLS fingerprints currently in rotation (read-only convenience).
CLIENT_IDENTIFIERS = tuple(p["client_identifier"] for p in BROWSER_PROFILES)

#: A representative header set, for inspection or copying.
BROWSER_HEADERS = dict(BROWSER_PROFILES[0]["headers"])


def profile_headers(profile, extra=None):
    """Headers for ``profile`` with :data:`EXTRA_HEADERS` and ``extra`` merged in."""
    headers = dict(profile["headers"])
    if EXTRA_HEADERS:
        headers.update(EXTRA_HEADERS)
    if extra:
        headers.update(extra)
    return headers
