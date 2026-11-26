from __future__ import annotations

import re
from urllib.parse import urlparse

PLATFORM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("youtube", re.compile(r"(?:youtube\.com|youtu\.be)", re.I)),
    ("facebook", re.compile(r"(?:facebook\.com|fb\.watch|fb\.com)", re.I)),
    ("tiktok", re.compile(r"(?:tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)", re.I)),
    ("x", re.compile(r"(?:twitter\.com|x\.com|t\.co)", re.I)),
    ("instagram", re.compile(r"instagram\.com", re.I)),
    ("threads", re.compile(r"threads\.(?:net|com)", re.I)),
]


def detect_platform(url: str) -> str | None:
    host_path = urlparse(url).netloc + urlparse(url).path
    for name, pattern in PLATFORM_PATTERNS:
        if pattern.search(host_path) or pattern.search(url):
            return name
    return None
