"""Quick multi-platform demo. Run: python examples/demo_urls.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from socmeta import extract_many
from socmeta.schema import public_row

URLS = [
    "https://www.instagram.com/p/DfpElgUJ4IT/",
    "https://vt.tiktok.com/ZSpx5mTDg/",
    "https://www.threads.com/share/IBF-lfk7L",
    "https://x.com/SmwGwOto/status/2121022732225655075",
    "https://www.facebook.com/reel/2450924395729778",
    "https://www.instagram.com/reel/DftBJ5JSuUU/",
    "https://www.facebook.com/1196569832482373/posts/1633759505430068",
]


def main() -> None:
    rows = extract_many(URLS)
    for row in rows:
        print(json.dumps(public_row(row), ensure_ascii=False))
        print("---")


if __name__ == "__main__":
    main()
