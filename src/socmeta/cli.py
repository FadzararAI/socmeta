from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .extract import extract_many
from .schema import FIELD_COVERAGE, public_row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="socmeta",
        description="Extract public social post metadata (likes, comments, followers, …).",
    )
    parser.add_argument("urls", nargs="*", help="Post URL(s)")
    parser.add_argument("--cookies-from-browser", default=None)
    parser.add_argument("--cookiefile", default=None)
    parser.add_argument("--no-enrich", action="store_true", help="Skip author→followers lookup")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--coverage", action="store_true", help="Print field coverage matrix")
    parser.add_argument("--version", action="version", version=f"socmeta {__version__}")
    args = parser.parse_args(argv)

    if args.coverage:
        print(json.dumps(FIELD_COVERAGE, indent=2))
        return 0
    if not args.urls:
        parser.error("at least one URL is required (or pass --coverage)")

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


if __name__ == "__main__":
    sys.exit(main())
