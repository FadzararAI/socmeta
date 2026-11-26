from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .extract import extract_many
from .schema import FIELD_COVERAGE, public_row


def _cmd_post(args: argparse.Namespace) -> int:
    if args.coverage:
        print(json.dumps(FIELD_COVERAGE, indent=2))
        return 0
    if not args.urls:
        raise SystemExit("at least one post URL is required (or pass --coverage)")

    rows = extract_many(
        args.urls,
        enrich=not args.no_enrich,
        cookies_from_browser=args.cookies_from_browser,
        cookiefile=args.cookiefile,
        verbose=args.verbose,
    )
    printable = [public_row(r) for r in rows]
    print(json.dumps(printable if len(printable) > 1 else printable[0], indent=2, ensure_ascii=False))
    return 0 if all(r.get("status") != "fail" for r in rows) else 1


def _cmd_profile(args: argparse.Namespace) -> int:
    from .profile import profile_posts

    result = profile_posts(
        args.ref,
        platform=args.platform,
        limit=args.limit,
        enrich=args.enrich,
        cookies_from_browser=args.cookies_from_browser,
        cookiefile=args.cookiefile,
        verbose=args.verbose,
    )
    # Compact posts for CLI unless --full
    out = {
        "platform": result.get("platform"),
        "username": result.get("username"),
        "display_name": result.get("display_name"),
        "followers": result.get("followers"),
        "profile_url": result.get("profile_url"),
        "count": result.get("count"),
        "source": result.get("source"),
        "note": result.get("note"),
        "status": result.get("status"),
        "posts": [
            public_row(p) if args.enrich else {
                k: p.get(k)
                for k in (
                    "platform", "url", "id", "username", "caption", "likes",
                    "comments", "reposts", "shares", "bookmarks", "views",
                    "post_date", "status", "error",
                )
                if k in p or p.get(k) is not None
            }
            for p in (result.get("posts") or [])
        ],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if result.get("status") != "fail" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="socmeta",
        description="Extract public social post metadata and profile feeds.",
    )
    parser.add_argument("--version", action="version", version=f"socmeta {__version__}")
    sub = parser.add_subparsers(dest="command")

    # Default / legacy: post URLs as positional args (no subcommand)
    parser.add_argument("urls", nargs="*", help="Post URL(s) (default command)")
    parser.add_argument("--cookies-from-browser", default=None)
    parser.add_argument("--cookiefile", default=None)
    parser.add_argument("--no-enrich", action="store_true", help="Skip author→followers lookup")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--coverage", action="store_true", help="Print field coverage matrix")

    p_profile = sub.add_parser("profile", help="List recent posts from a profile")
    p_profile.add_argument("ref", help="Profile URL or @handle")
    p_profile.add_argument(
        "--platform",
        choices=["youtube", "tiktok", "x", "instagram", "threads", "facebook"],
        help="Required when ref is a bare @handle",
    )
    p_profile.add_argument("--limit", type=int, default=12, help="Max posts (default 12)")
    p_profile.add_argument(
        "--enrich",
        action="store_true",
        help="Re-scrape each post for full engagement metrics",
    )
    p_profile.add_argument("--cookies-from-browser", default=None)
    p_profile.add_argument("--cookiefile", default=None)
    p_profile.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "profile":
        return _cmd_profile(args)

    # Default: treat as post extraction (back-compat)
    return _cmd_post(args)


if __name__ == "__main__":
    sys.exit(main())
