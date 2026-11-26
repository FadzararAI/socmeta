"""socmeta — public social post metadata (likes, comments, followers, …).

Workflows
---------
Post:
  1. Detect platform from the post URL.
  2. Extract engagement + caption + author from the post page.
  3. If followers are missing, resolve author profile → followers.

Profile:
  profile URL / @handle → recent posts list (optional per-post enrich).
"""

from .extract import extract, extract_many
from .followers import author_from_post, enrich_followers
from .profile import profile_posts

__version__ = "0.1.1"
__all__ = [
    "extract",
    "extract_many",
    "profile_posts",
    "author_from_post",
    "enrich_followers",
    "__version__",
]
