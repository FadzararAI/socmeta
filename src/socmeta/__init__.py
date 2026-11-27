"""socmeta — public social post metadata (likes, comments, followers, …).

Post workflow
-------------
  1. Detect platform from the post URL.
  2. Extract engagement + caption + author from the post page.
  3. If followers are missing, resolve author profile → followers.

Comments workflow
-----------------
  post URL → top-level comments (optional --include-replies)

Profile feeds live in the separate ``socfeed`` package/runtime.
"""

from .comments import extract_comments, extract_comments_many
from .extract import extract, extract_many
from .followers import author_from_post, enrich_followers

__version__ = "0.2.0"
__all__ = [
    "extract",
    "extract_many",
    "extract_comments",
    "extract_comments_many",
    "author_from_post",
    "enrich_followers",
    "__version__",
]
