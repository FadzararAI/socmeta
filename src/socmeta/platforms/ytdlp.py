from __future__ import annotations

from typing import Any

import yt_dlp

from socmeta.normalize import normalize_ytdlp
from socmeta.ytdlp_patch import apply as apply_ytdlp_patch


def extract_via_ytdlp(
    url: str,
    *,
    platform: str,
    cookies_from_browser: str | None = None,
    cookiefile: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    apply_ytdlp_patch()

    opts: dict[str, Any] = {
        "quiet": not verbose,
        "no_warnings": not verbose,
        "skip_download": True,
        "ignoreerrors": False,
        "extract_flat": False,
        "ignore_no_formats_error": True,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if cookiefile:
        opts["cookiefile"] = cookiefile

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise RuntimeError(f"No metadata returned for {url}")
        if info.get("_type") == "playlist" and info.get("entries"):
            entries = [e for e in info["entries"] if e]
            if len(entries) == 1:
                info = entries[0]
        return normalize_ytdlp(info, url=url, platform=platform)
