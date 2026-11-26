"""socmeta — public social post metadata (likes, comments, followers, …).

Workflow
--------
1. Detect platform from the post URL.
2. Extract engagement + caption + author from the post page.
3. If followers are missing, resolve author profile → followers
   (post → author → followers).
"""

from .extract import extract, extract_many
from .followers import author_from_post, enrich_followers

__version__ = "0.1.0"
__all__ = [
    "extract",
    "extract_many",
    "author_from_post",
    "enrich_followers",
    "__version__",
]
