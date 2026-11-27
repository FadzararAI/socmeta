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
        raise SystemExit(
            "at least one post URL is required (or pass --coverage).\n"
            "Comments:  socmeta comments <post-url>\n"
            "Profiles:  socfeed <profile-url>"
        )

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


def _cmd_comments(args: argparse.Namespace) -> int:
    from .comments import extract_comments_many

    results = extract_comments_many(
        args.urls,
        limit=args.limit,
        include_replies=args.include_replies,
        replies_limit=args.replies_limit,
        sort=args.sort,
        ranking_mode=args.ranking,
    )
    printable = results if len(results) > 1 else results[0]
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    return 0 if all(r.get("status") != "fail" for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="socmeta",
        description="Extract public social post metadata and comments from a post URL.",
    )
    parser.add_argument("--version", action="version", version=f"socmeta {__version__}")
    sub = parser.add_subparsers(dest="command")

    # Default: post URLs as positional args (no subcommand)
    parser.add_argument("urls", nargs="*", help="Post URL(s) (default command)")
    parser.add_argument("--cookies-from-browser", default=None)
    parser.add_argument("--cookiefile", default=None)
    parser.add_argument("--no-enrich", action="store_true", help="Skip author→followers lookup")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--coverage", action="store_true", help="Print field coverage matrix")

    p_comments = sub.add_parser("comments", help="Extract comments from post URL(s)")
    p_comments.add_argument("urls", nargs="+", help="Post URL(s)")
    p_comments.add_argument("--limit", type=int, default=50, help="Max top-level comments (default 50)")
    p_comments.add_argument(
        "--include-replies",
        action="store_true",
        help="Also fetch replies under each comment (off by default)",
    )
    p_comments.add_argument(
        "--replies-limit",
        type=int,
        default=20,
        help="Max replies per comment when --include-replies (default 20)",
    )
    p_comments.add_argument(
        "--sort",
        choices=["newest", "top", "relevant"],
        default="newest",
        help="Comment order: newest (default), top (by likes), or relevant (platform ranking)",
    )
    p_comments.add_argument(
        "--ranking",
        choices=["likes", "recency"],
        default=None,
        help="X only: override fetch ranking (recency/likes). Default follows --sort.",
    )

    args = parser.parse_args(argv)

    if args.command == "comments":
        return _cmd_comments(args)

    return _cmd_post(args)


if __name__ == "__main__":
    sys.exit(main())
