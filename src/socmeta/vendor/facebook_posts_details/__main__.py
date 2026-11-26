"""Allow ``python -m facebook_posts_details <url>``."""

from __future__ import annotations

from .cli import _entrypoint

if __name__ == "__main__":
    raise SystemExit(_entrypoint())
