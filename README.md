# socmeta

Extract **public** social post metadata from a **post URL** — likes, comments, shares/reposts, bookmarks, views, caption, post date, and author followers — plus **public comment threads**.

No login required for public posts.

For **profile feeds** and **keyword/hashtag discovery**, use **[socfeed](https://github.com/FadzararAI/socfeed)**.

Full metrics matrix, parameters, rate limits, and platform blockers: **[docs/CAPABILITIES.md](docs/CAPABILITIES.md)**.

## Workflow

```
post URL → detect platform → engagement + author
         → if followers missing → author profile → followers

post URL → comments (optional replies, --sort newest|top|relevant)
```

| Platform  | Post metrics                         | Followers                         |
|-----------|--------------------------------------|-----------------------------------|
| YouTube   | yt-dlp                               | embedded on post                  |
| TikTok    | yt-dlp (+ share/save mapping)        | embedded on post                  |
| X         | yt-dlp (+ bookmarks)                 | embedded / feed                   |
| Instagram | yt-dlp                               | profile lookup                    |
| Facebook  | vendored FB page parser              | profile                           |
| Threads   | vendored Threads parser              | profile lookup                    |

## Install

```bash
pip install -e .
```

## CLI

```bash
socmeta "https://www.instagram.com/p/XXXX/"
socmeta URL1 URL2 URL3
socmeta --coverage

# comments (bulk OK; replies off by default)
socmeta comments "https://www.youtube.com/watch?v=VIDEO_ID" --limit 20
socmeta comments URL1 URL2 --limit 20 --sort top
socmeta comments "https://www.tiktok.com/@user/video/123" --limit 50 --sort top
socmeta comments "https://www.facebook.com/.../posts/..." --include-replies --limit 20 --sort newest
socmeta comments "https://www.threads.com/@user/post/CODE" --limit 15 --sort relevant
socmeta comments "https://www.instagram.com/p/SHORTCODE/" --limit 100
socmeta comments "https://x.com/user/status/123" --limit 20 --sort top
```

### Comment parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--limit` | `50` | Max top-level comments |
| `--include-replies` | off | Also fetch nested replies |
| `--replies-limit` | `20` | Max replies per comment |
| `--sort` | `newest` | `newest` · `top` · `relevant` |
| `--ranking` | follows sort | X only: `recency` or `likes` |

## Python

```python
from socmeta import extract, extract_comments, extract_comments_many

row = extract("https://x.com/user/status/123")
print(row["likes"], row["followers"], row["author_profile"])

thread = extract_comments(
    "https://www.tiktok.com/@user/video/123",
    limit=50,
    include_replies=False,
    sort="top",  # newest | top | relevant
)
for c in thread["comments"]:
    print(c["username"], c["text"], c["likes"])

threads = extract_comments_many([URL1, URL2], limit=20, sort="newest")
```

## Output fields

`platform`, `url`, `username`, `display_name`, `author_profile`, `caption`, `likes`, `comments`, `reposts`, `shares`, `bookmarks`, `views`, `followers`, `followers_source`, `post_date`, `status`

## Known limits (summary)

- Public content only — private / friends-only posts fail.
- Bulk runs are sequential; heavy traffic can hit soft rate limits or empty responses.
- Instagram comments often lack like counts and deeper pages when logged out.
- X conversation fetch fails for deleted/withheld (“tombstone”) posts.
- See **[docs/CAPABILITIES.md](docs/CAPABILITIES.md)** for the full matrix and per-platform blockers.

## Notes

- X has no public “shares” metric (use `reposts` + `bookmarks`).
- TikTok UI “Shares” maps to `shares`; saves map to `bookmarks`.
- See [NOTICE](NOTICE) for third-party attributions.

## License

MIT — see [LICENSE](LICENSE).
