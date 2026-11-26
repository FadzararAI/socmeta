"""Command line interface.

    facebook-posts-details <url> [<url> ...] [options]
    python -m facebook_posts_details <url>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from . import __doc__ as _pkg_doc
from . import __version__, scrape

__all__ = ["main"]


def summarise(data):
    """One dense block per result -- easier to scan than the full JSON."""
    if not data:
        return "  -> None"
    if "post_type" in data:                                    # a post
        return (
            f"  type={data['post_type']}  id={data['post_id']}\n"
            f"  likes={data['likes_count']}  comments={data['comments_count']}  "
            f"shares={data['share_count']}  views={data['views_count']}\n"
            f"  images={len(data['post_images'])}  "
            f"video={'yes' if data['video_url'] else 'no'}  "
            f"transcript={'yes' if data['transcript'] else 'no'}\n"
            f"  date={data['publish_date_iso']}\n"
            f"  by={data['name']!r}\n"
            f"  text={str(data['post_text'])[:120]!r}"
        )
    if "followers" in data:                                    # a profile
        return (
            f"  name={data['name']!r}  id={data['profile_id_number']}\n"
            f"  followers={data['followers']}  following={data['following']}  "
            f"verified={data['is_verified']}  gender={data['gender']}\n"
            f"  category={data['category_name']!r}  photos={len(data['photos'])}\n"
            f"  about={list(data['about_section'])}\n"
            f"  bio={str(data['bio'])[:120]!r}"
        )
    return f"  about tabs: {list(data)}"                        # merged about


def build_parser():
    parser = argparse.ArgumentParser(
        prog="facebook-posts-details",
        description=(_pkg_doc or "").strip().split("\n")[0],
    )
    parser.add_argument("url", nargs="+",
                        help="Facebook post, reel, video, photo or profile URL(s)")
    parser.add_argument("-k", "--kind", default="auto",
                        choices=("auto", "post", "profile", "about"),
                        help="what to scrape (default: guess from the URL)")
    parser.add_argument("-p", "--with-profile", action="store_true",
                        help="for posts, also scrape the author's profile "
                             "into the 'user' key")
    parser.add_argument("-s", "--summary", action="store_true",
                        help="print a summary block instead of full JSON")
    parser.add_argument("-x", "--proxy", default=None,
                        help="proxy for every request: a full URL like "
                             "http://user:pass@host:port, or host:port")
    parser.add_argument("-t", "--timeout", type=float, default=None,
                        help="per-request timeout in seconds")
    parser.add_argument("-r", "--retries", type=int, default=None,
                        help="attempts per request")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="log progress to stderr")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    return parser


def main(argv=None):
    args = build_parser().parse_args(sys.argv[1:] if argv is None else list(argv))

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    failures = 0
    for url in args.url:
        started = datetime.now()
        try:
            data = scrape(url, args.kind, with_profile=args.with_profile,
                          timeout=args.timeout, retries=args.retries,
                          proxy=args.proxy)
        except KeyboardInterrupt:
            raise
        except Exception:
            logging.getLogger(__name__).exception("scrape failed for %s", url)
            data = None
        failures += data is None

        elapsed = datetime.now() - started
        if len(args.url) > 1 or args.summary:
            print(f"\n=== {url}\n    ({args.kind}, {elapsed})")
        if args.summary:
            print(summarise(data))
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        if len(args.url) == 1 and not args.summary:
            sys.stdout.flush()  # keep the JSON ahead of this note when piped
            print(f"\nelapsed: {elapsed}", file=sys.stderr)

    return 1 if failures else 0


def _entrypoint() -> int:  # pragma: no cover - thin console-script wrapper
    """Console-script target: keep a broken pipe or Ctrl-C from dumping a traceback."""
    try:
        return main()
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(_entrypoint())
