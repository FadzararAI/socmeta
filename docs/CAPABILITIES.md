# socmeta — capabilities, metrics, and limitations

`socmeta` extracts **public** post metadata and **public** comment threads from a post URL. It does not log in. Profile feeds and keyword discovery live in the sister package [`socfeed`](https://github.com/FadzararAI/socfeed).

This document describes what works today, which metrics are available, the CLI/API parameters, and the known limits and failure modes.

---

## Scope

| Capability | Status | Entry point |
|------------|--------|-------------|
| Post metadata (likes, caption, date, …) | Working — 6 platforms | `socmeta <url…>` / `extract()` / `extract_many()` |
| Comment threads | Working — 6 platforms | `socmeta comments <url…>` / `extract_comments()` / `extract_comments_many()` |
| Profile feeds | Separate package | [`socfeed`](https://github.com/FadzararAI/socfeed) |
| Keyword / hashtag discovery | Separate package (partial) | [`socfeed` search/hashtag](https://github.com/FadzararAI/socfeed) |

Supported platforms: **YouTube, TikTok, X, Instagram, Facebook, Threads**.

---

## Post metadata

### Workflow

```
post URL → detect platform → engagement + caption + author
         → if followers missing → author profile lookup → followers
```

Bulk input is supported: pass multiple URLs on the CLI or use `extract_many([...])`. Failures become `status: fail` rows so a batch can continue.

### Metrics (field coverage)

| Field | YouTube | TikTok | X | Instagram | Facebook | Threads |
|-------|:-------:|:------:|:-:|:---------:|:--------:|:-------:|
| `likes` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `comments` (count) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `views` | ✓ | ✓ | ✓ | partial | ✓ | ✓* |
| `shares` | — | ✓ | — | — | ✓ | ✓ |
| `reposts` | — | — | ✓ | — | — | ✓ |
| `bookmarks` | — | ✓ (saves) | ✓ | — | — | — |
| `followers` | ✓ | ✓ | ✓ | ✓ (profile) | ✓ (profile) | ✓ (profile) |
| `post_date` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `caption` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

\*Threads view counts are often only present for the author or via specific permalink fields; logged-out pulls may leave `views` null.

**Platform notes**

- **X** has no public “shares” metric; use `reposts` + `bookmarks`.
- **TikTok** UI “Shares” → `shares`; saves → `bookmarks`.
- **Instagram** views are partial (often reels-oriented); likes may be hidden by the creator.
- Private, deleted, geo-blocked, or login-gated posts return `status: fail`.

### Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| URL(s) | required | One or more post URLs |
| `--no-enrich` | off | Skip author→followers lookup when followers are missing |
| `--cookies-from-browser` | none | Optional browser cookie jar (yt-dlp style) for gated pages |
| `--cookiefile` | none | Optional Netscape cookie file |
| `-v` / `--verbose` | off | Extra extractor logging |
| `--coverage` | — | Print the field-coverage matrix as JSON |

### Limitations (post extract)

| Limit | Why |
|-------|-----|
| Public posts only | No session login; private / friends-only content is out of scope |
| Soft rate limits | Platforms throttle anonymous clients. Bulk runs are sequential; heavy parallel use can yield 429s, empty bodies, or temporary blocks |
| Cookie / region variance | Some posts render differently by IP region or require cookies for full HTML |
| Instagram fragility | Logged-out Instagram often serves a thin page or login wall; metrics may be incomplete |
| Text-only Facebook posts | Some text posts expose fewer media fields than reels/videos |

---

## Comments

### Workflow

```
post URL → platform comment API / page → top-level comments
         → optional nested replies
         → --sort newest | top | relevant
```

Bulk input is supported (`socmeta comments URL1 URL2 …`).

### Comment object (typical fields)

`id`, `text`, `likes`, `created_at`, `username`, `display_name`, `profile_url` (when available), `reply_count`, optional nested `replies[]`.

### Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| URL(s) | required | One or more post URLs |
| `--limit` | `50` | Max **top-level** comments |
| `--include-replies` | off | Also fetch replies under each comment |
| `--replies-limit` | `20` | Max replies per parent when replies are on |
| `--sort` | `newest` | `newest` · `top` (by likes) · `relevant` (platform ranking when available) |
| `--ranking` | follows `--sort` | **X only** override of fetch ranking: `recency` or `likes` |

**How `--sort` is applied**

| Mode | Behavior |
|------|----------|
| `newest` | Order by `created_at` descending (YouTube uses yt-dlp `comment_sort=new`; Facebook uses chronological intent; X fetches `recency`) |
| `top` | Prefer likes (YouTube `comment_sort=top`; X likes ranking; Facebook unfiltered ranked list + client likes sort; others client-side by likes) |
| `relevant` | Keep platform ranking when the fetch already ranked (YouTube top sort, Facebook “Most relevant”, X likes ranking); otherwise preserve fetch order |

### Per-platform comment behavior

| Platform | Source | Replies | Sort support | Notable limits |
|----------|--------|---------|--------------|----------------|
| YouTube | yt-dlp `getcomments` | Optional | Native new/top | Totals come from metadata first (fetch caps must not overwrite `comment_count`) |
| TikTok | Web `comment/list` (+ reply list) | Optional | Client-side (API feed order + local sort) | Needs a warm session; empty or challenged pages fail |
| Facebook | SSR + GraphQL UFI | Optional | Native intents (newest / relevant / all) + local likes for `top` | “Most relevant” filters some comments; logged-out depth varies |
| Threads | Permalink / GraphQL blobs | Optional | Client-side | Logged-out reply depth is shallow (often one page) |
| Instagram | Logged-out GraphQL / page | Optional | Client-side | Often **likes = 0** logged out; may fetch only a subset (~dozen+) without login |
| X | FixTweet conversation API | Optional (nested when present in pages) | Fetch `recency`/`likes` + local sort | Deleted / withheld tweets → conversation 404 (“tombstone”); no official search-backed comments |

### Limitations (comments)

| Limit | Why |
|-------|-----|
| Replies off by default | Keeps calls cheaper and faster; nested fetch multiplies requests |
| Instagram engagement gaps | Meta withholds like counts and deeper pagination for anonymous clients |
| Facebook filtering | Ranked intents intentionally hide “low quality” / spam-shaped comments |
| Soft bot gates | Unusual IPs or fast bulk may get empty JSON (`status_code` errors) rather than HTTP 403 |
| No authenticated mode | Full IG/FB comment history often requires a real user session — out of scope for this package |

---

## Error model

Successful rows use `status: "ok"`. Failures use `status: "fail"` with an `error` string. Bulk helpers never abort the whole batch on a single bad URL.

---

## Related

- Field matrix CLI: `socmeta --coverage`
- Profile feeds & discovery: [socfeed CAPABILITIES](https://github.com/FadzararAI/socfeed/blob/main/docs/CAPABILITIES.md)
- Third-party notices: [NOTICE](../NOTICE)
