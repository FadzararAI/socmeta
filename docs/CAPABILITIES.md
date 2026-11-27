# socmeta — capabilities by feature

`socmeta` covers **post extraction** and **comment scraping** from a public post URL.  
Profile feeds and keyword/hashtag discovery live in [`socfeed`](https://github.com/FadzararAI/socfeed) — see that repo’s [CAPABILITIES](https://github.com/FadzararAI/socfeed/blob/main/docs/CAPABILITIES.md).

No login is used. Each section below is self-contained: what it does, metrics, parameters, limits, challenges, and blockers.

---

# 1. Post extractor

**Status:** Working on YouTube, TikTok, X, Instagram, Facebook, Threads.  
**Entry points:** `socmeta <url…>` · `extract()` · `extract_many()`

## 1.1 What it does

Given one or more **post URLs**, detect the platform, pull engagement + caption + author, then (unless disabled) resolve **followers** from the author profile when the post page did not embed them.

```
post URL → platform → likes / comments / views / … + caption + author
        → optional followers enrich from author profile
```

Bulk is supported. A failed URL becomes `status: "fail"` and the batch continues.

## 1.2 Metrics

| Field | YouTube | TikTok | X | Instagram | Facebook | Threads |
|-------|:-------:|:------:|:-:|:---------:|:--------:|:-------:|
| `likes` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `comments` (count) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `views` | ✓ | ✓ | ✓ | partial | ✓ | partial* |
| `shares` | — | ✓ | — | — | ✓ | ✓ |
| `reposts` | — | — | ✓ | — | — | ✓ |
| `bookmarks` | — | ✓ (saves) | ✓ | — | — | — |
| `followers` | ✓ | ✓ | ✓ | ✓ (via profile) | ✓ (via profile) | ✓ (via profile) |
| `post_date` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `caption` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `username` / `display_name` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

\*Threads `views` are often author-only or missing for logged-out clients.

**Mapping quirks**

- **X:** no public “shares”; use `reposts` + `bookmarks`.
- **TikTok:** UI Shares → `shares`; saves → `bookmarks`.
- **Instagram:** likes may be hidden by the creator; views are reel-oriented / partial.

## 1.3 Parameters

| Parameter | Default | Detail |
|-----------|---------|--------|
| URL(s) | required | One or more post permalinks |
| `--no-enrich` | off | Skip author→followers lookup |
| `--cookies-from-browser` | none | Optional browser cookies (yt-dlp) |
| `--cookiefile` | none | Netscape cookie file |
| `-v` / `--verbose` | off | Extra logging |
| `--coverage` | — | Dump this field-coverage matrix as JSON |

Python: `extract(url, enrich=True, cookies_from_browser=…, cookiefile=…)` · `extract_many(urls, …)`.

## 1.4 Limits

| Limit | Detail |
|-------|--------|
| Public posts only | Private, friends-only, or age-gated posts are out of scope |
| Sequential bulk | `extract_many` runs one URL after another; safer against bans, slower for large lists |
| Soft platform quotas | Anonymous clients get throttled; symptoms are timeouts, 429s, or empty/partial HTML |
| Region / cookie variance | The same URL can render different fields by egress country or cookie state |
| Text-only Facebook | Some text posts expose thinner media metadata than reels/videos |

## 1.5 Challenges

| Challenge | Detail |
|-----------|--------|
| Keeping extractors fresh | yt-dlp and Meta page shapes change; a green path today can break after a frontend deploy |
| Followers not always on the post | IG / FB / Threads often need a second request to the author profile |
| Inconsistent “share” semantics | Platforms invent different counters; we normalize into `shares` / `reposts` / `bookmarks` with documented mapping |
| Partial success | A post can return `status: ok` with some null fields when the page simply does not show that metric |

## 1.6 Blockers (when post extract fails)

| Blocker | Why it happens | What would make it work |
|---------|----------------|-------------------------|
| Private / deleted post | Content is not in the public HTML/API | A session that can see it (login) — **out of scope** |
| Instagram login wall on the post page | Meta serves a login shell instead of media JSON for some IPs/UAs | Residential egress and/or cookies; still fragile without login |
| Geo / copyright block | Platform returns a block page | Exit IP in an allowed region |
| yt-dlp extractor outage | Upstream site marked broken | Wait for yt-dlp fix, or temporary cookies |

---

# 2. Comments scraper

**Status:** Working on YouTube, TikTok, X, Instagram, Facebook, Threads.  
**Entry points:** `socmeta comments <url…>` · `extract_comments()` · `extract_comments_many()`

## 2.1 What it does

Given one or more **post URLs**, fetch **top-level comments** (and optionally nested replies), then apply `--sort`.

```
post URL → comment list API / page → top-level comments
        → optional replies under each comment
        → sort: newest | top | relevant
```

## 2.2 Metrics (per comment)

Typical fields: `id`, `text`, `likes`, `created_at`, `username`, `display_name`, `profile_url`, `reply_count`, optional `replies[]`.

Thread-level fields: `platform`, `url`, `count`, `total` (when known), `sort`, `include_replies`, `status`, `note`.

## 2.3 Parameters

| Parameter | Default | Detail |
|-----------|---------|--------|
| URL(s) | required | One or more post URLs |
| `--limit` | `50` | Max **top-level** comments |
| `--include-replies` | off | Also fetch replies |
| `--replies-limit` | `20` | Cap per parent when replies are on |
| `--sort` | `newest` | `newest` · `top` (likes) · `relevant` (platform ranking when available) |
| `--ranking` | follows `--sort` | **X only:** force fetch mode `recency` or `likes` |

**Sort behavior**

| `--sort` | Behavior |
|----------|----------|
| `newest` | By `created_at` desc; YouTube uses `comment_sort=new`; Facebook chronological intent; X fetches `recency` |
| `top` | Prefer likes; YouTube `comment_sort=top`; X likes ranking; Facebook ranked/unfiltered + client likes; others client-side |
| `relevant` | Preserve platform ranking when the fetch was already ranked; else keep fetch order |

## 2.4 Per-platform details

| Platform | Source | Replies | Native sort hooks |
|----------|--------|---------|-------------------|
| YouTube | yt-dlp `getcomments` | Optional | `comment_sort` new/top |
| TikTok | Web comment + reply list APIs | Optional | Client-side after fetch |
| Facebook | Permalink SSR + UFI GraphQL | Optional | Intent tokens (newest / most relevant / all) |
| Threads | Permalink / embedded GraphQL | Optional | Client-side |
| Instagram | Logged-out GraphQL / page | Optional | Client-side |
| X | FixTweet conversation API | Optional when nested IDs appear in pages | Fetch `recency` / `likes` |

## 2.5 Limits

| Limit | Detail |
|-------|--------|
| Top-level first | Replies are off by default to control cost |
| `--include-replies` multiplies requests | Roughly `parents × reply pages` |
| Instagram like counts often `0` | Logged-out APIs omit diggs; `--sort top` is weak on IG |
| Instagram depth | Anonymous clients often get only a short first page (~dozens), not full threads |
| Facebook “Most relevant” | Intentionally filters spam / low-quality; `total` can exceed returned rows |
| Threads reply depth | Logged-out replies are often a single shallow page |
| X tombstones | Deleted/withheld root tweets make the conversation endpoint 404 |
| Soft rate limits | Fast bulk comment pulls can empty out mid-batch |

## 2.6 Challenges

| Challenge | Detail |
|-----------|--------|
| Ranking ≠ completeness | `relevant` / Facebook ranked intents trade coverage for “quality” |
| Client-side sort on capped windows | Sorting 50 fetched comments is not the same as “top comments on the whole post” |
| Keeping GraphQL `doc_id`s / FixTweet shapes current | Meta and FixTweet change without notice |
| Separating “no comments” from “gated empty” | Both can look like `count: 0`; notes/errors try to distinguish |

## 2.7 Blockers (when comments fail or degrade)

| Blocker | Why | What’s needed |
|---------|-----|----------------|
| Instagram login for full threads | Meta gates pagination and likes behind session | Logged-in cookies — **out of scope** for default socmeta |
| Facebook filtered intents | Product design, not a bug | Use `--sort newest` for broader chrono lists; still not guaranteed complete |
| X conversation unavailable | Tweet deleted, withheld, or FixTweet outage | Different URL / wait / alternate provider |
| TikTok empty comment JSON | Challenge page or cold session | Warm video page / retry; rarely residential IP |
| Comments disabled on the post | Creator or platform setting | Nothing to scrape |

---

# 3. Related packages (not in socmeta)

| Feature | Package | Doc |
|---------|---------|-----|
| Profile → recent posts | [`socfeed`](https://github.com/FadzararAI/socfeed) | [Profile section](https://github.com/FadzararAI/socfeed/blob/main/docs/CAPABILITIES.md#1-profile-scraper) |
| Keyword / hashtag discovery | [`socfeed`](https://github.com/FadzararAI/socfeed) | [Keywords section](https://github.com/FadzararAI/socfeed/blob/main/docs/CAPABILITIES.md#2-keywords--hashtag-discovery-ongoing) |

---

## Error model

- `status: "ok"` — row produced (fields may still be null).
- `status: "fail"` — extraction aborted for that URL; see `error`.
- Bulk helpers never abort the whole list on one failure.

## License / notices

MIT — [LICENSE](../LICENSE). Third-party attributions — [NOTICE](../NOTICE).
