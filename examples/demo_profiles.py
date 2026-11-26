"""Demo profile feeds. Run: python examples/demo_profiles.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from socmeta import profile_posts

SAMPLES = [
    ("https://www.tiktok.com/@uzoneindonesia", None, 5),
    ("@SmwGwOto", "x", 5),
    ("https://www.instagram.com/hujat_otomotiff/", None, 5),
    ("@smwgwoto", "threads", 5),
    ("https://www.facebook.com/OFFICIALSETIRKANAN", None, 5),
    ("https://www.youtube.com/@MrBeast/videos", None, 3),
]


def main() -> None:
    for ref, platform, limit in SAMPLES:
        print(f"\n>>> {platform or 'auto'} {ref}", flush=True)
        try:
            feed = profile_posts(ref, platform=platform, limit=limit)
            summary = {
                "platform": feed.get("platform"),
                "username": feed.get("username"),
                "followers": feed.get("followers"),
                "count": feed.get("count"),
                "source": feed.get("source"),
                "posts": [
                    {
                        "url": p.get("url"),
                        "likes": p.get("likes"),
                        "comments": p.get("comments"),
                        "views": p.get("views"),
                        "caption": (p.get("caption") or "")[:60],
                    }
                    for p in (feed.get("posts") or [])[:limit]
                ],
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
