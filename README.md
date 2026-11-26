# socmeta

Extract **public** social post metadata from a URL — likes, comments, shares/reposts, bookmarks, views, caption, post date, and author followers.

No login required for public posts.

## Workflow

```
post URL
   │
   ├─ detect platform
   ├─ scrape post engagement + author handle
   └─ if followers missing → author profile → followers
```

| Platform  | Post metrics                         | Followers                         |
|-----------|--------------------------------------|-----------------------------------|
| YouTube   | yt-dlp                               | embedded on post                  |
| TikTok    | yt-dlp (+ share/save mapping)        | embedded on post                  |
| X         | yt-dlp (+ bookmarks)                 | embedded on post                  |
| Instagram | yt-dlp                               | profile lookup from author handle |
| Facebook  | vendored FB page parser              | profile (with post)               |
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
```

## Python

```python
from socmeta import extract

row = extract("https://x.com/user/status/123")
print(row["likes"], row["followers"], row["author_profile"])
```

## Output fields

`platform`, `url`, `username`, `display_name`, `author_profile`, `caption`, `likes`, `comments`, `reposts`, `shares`, `bookmarks`, `views`, `followers`, `followers_source`, `post_date`, `status`

## Notes

- Text-only / private / login-walled posts may fail.
- X has no public “shares” metric (use `reposts` + `bookmarks`).
- TikTok UI “Shares” maps to `shares`; saves map to `bookmarks`.
- See [NOTICE](NOTICE) for third-party attributions.

## License

MIT — see [LICENSE](LICENSE).
