"""Runtime patches so stock yt-dlp exposes bookmarks + author followers.

Stock yt-dlp already scrapes X/TikTok payloads that contain these fields but
does not always map them onto the info dict. We patch the extractors once —
no fork required.
"""

from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return

    from yt_dlp.extractor import tiktok as tiktok_mod
    from yt_dlp.extractor.twitter import TwitterIE
    from yt_dlp.utils import int_or_none, traverse_obj

    # --- X / Twitter: capture status, then fill bookmark + followers ----------
    if hasattr(TwitterIE, "_extract_status"):
        _orig_status = TwitterIE._extract_status

        def _extract_status(self, *args, **kwargs):  # noqa: ANN001
            status = _orig_status(self, *args, **kwargs)
            self._socmeta_last_status = status
            return status

        TwitterIE._extract_status = _extract_status

    _orig_twitter = TwitterIE._real_extract

    def _twitter_real_extract(self, url):  # noqa: ANN001
        info = _orig_twitter(self, url)
        status = getattr(self, "_socmeta_last_status", None)
        if status:
            user = status.get("user") or {}
            if info.get("bookmark_count") is None:
                info["bookmark_count"] = int_or_none(status.get("bookmark_count"))
            if info.get("channel_follower_count") is None:
                info["channel_follower_count"] = int_or_none(user.get("followers_count"))
        return info

    TwitterIE._real_extract = _twitter_real_extract

    # --- TikTok: author follower count from aweme / web stats ----------------
    TikTokIE = tiktok_mod.TikTokIE
    if hasattr(TikTokIE, "_parse_aweme_video_app"):
        _orig_app = TikTokIE._parse_aweme_video_app

        def _parse_app(self, aweme_detail, *args, **kwargs):  # noqa: ANN001
            info = _orig_app(self, aweme_detail, *args, **kwargs)
            if info.get("channel_follower_count") is None:
                info["channel_follower_count"] = traverse_obj(
                    aweme_detail, ("author", "follower_count", {int_or_none})
                )
            return info

        TikTokIE._parse_aweme_video_app = _parse_app

    if hasattr(TikTokIE, "_parse_aweme_video_web"):
        _orig_web = TikTokIE._parse_aweme_video_web

        def _parse_web(self, aweme_detail, *args, **kwargs):  # noqa: ANN001
            info = _orig_web(self, aweme_detail, *args, **kwargs)
            if info.get("channel_follower_count") is None:
                info["channel_follower_count"] = traverse_obj(
                    aweme_detail,
                    (
                        ("authorStatsV2", "followerCount", {int_or_none}),
                        ("authorStats", "followerCount", {int_or_none}),
                    ),
                    get_all=False,
                )
            return info

        TikTokIE._parse_aweme_video_web = _parse_web

    _APPLIED = True
