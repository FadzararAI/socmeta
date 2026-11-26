"""Instagram profile follower lookup (post engagement comes from yt-dlp)."""

from __future__ import annotations

import re

from curl_cffi import requests as crequests


def profile_followers(username: str) -> int | None:
    r = crequests.get(
        f"https://www.instagram.com/{username.lstrip('@')}/",
        impersonate="chrome",
        timeout=30,
        headers={
            "Accept-Language": "en-US,en;q=0.9",
            "X-IG-App-ID": "936619743392459",
        },
    )
    hits = [int(x) for x in re.findall(r'"follower_count"\s*:\s*(\d+)', r.text)]
    return hits[0] if hits else None
