# socmeta capabilities

Terms match [GLOSSARY.md](../GLOSSARY.md).

socmeta has two features:

1. Post Extract from a public Post URL.
2. Comment Threads from a public Post URL.

Profile Feeds live in [socfeed](https://github.com/FadzararAI/socfeed). Keywords / Hashtags are an ongoing socfeed feature. Progress and Blockers are summarized in [§3](#3-keywords--hashtag-scraper-ongoing--lives-in-socfeed). Full detail is in [socfeed CAPABILITIES §2](https://github.com/FadzararAI/socfeed/blob/main/docs/CAPABILITIES.md#2-keywords--hashtag-scraper-ongoing).

socmeta does not log in. Each section below states what it does, metrics, parameters, Limits, challenges, and Blockers.

---

# 1. Post Extract

Status: Working on YouTube, TikTok, X, Instagram, Facebook, and Threads.

Entry points: `socmeta <url…>` · `extract()` · `extract_many()`

## 1.1 Function

You give one or more Post URLs.
socmeta detects the platform and reads engagement, caption, and author.
Unless you disable Enrich, socmeta then resolves followers from the author Profile when the Post page did not embed them.

```
post URL → platform → likes / comments / views / … + caption + author
        → optional followers Enrich from author Profile
```

Bulk is supported. A failed URL becomes `status: "fail"`. The batch continues.

## 1.2 Metrics

| Field | YouTube | TikTok | X | Instagram | Facebook | Threads |
|-------|:-------:|:------:|:-:|:---------:|:--------:|:-------:|
| `likes` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `comments` (count) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `views` | ✓ | ✓ | ✓ | partial | ✓ | partial* |
| `shares` | — | ✓ | — | — | ✓ | ✓ |
| `reposts` | — | — | ✓ | — | — | ✓ |
| `bookmarks` | — | ✓ (saves) | ✓ | — | — | — |
| `followers` | ✓ | ✓ | ✓ | ✓ (via Profile) | ✓ (via Profile) | ✓ (via Profile) |
| `post_date` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `caption` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `username` / `display_name` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

\*Threads `views` are often author-only or missing for logged-out clients.

Mapping notes:

- X: no public shares field. Use `reposts` + `bookmarks`.
- TikTok: UI Shares → `shares`. Saves → `bookmarks`.
- Instagram: likes may be hidden by the creator. Views are reel-oriented / partial.

## 1.3 Parameters

| Parameter | Default | Detail |
|-----------|---------|--------|
| URL(s) | required | One or more Post permalinks |
| `--no-enrich` | off | Skip author → followers lookup |
| `--cookies-from-browser` | none | Optional browser cookies (yt-dlp) |
| `--cookiefile` | none | Netscape cookie file |
| `-v` / `--verbose` | off | Extra logging |
| `--coverage` | — | Dump this field-coverage matrix as JSON |

Python: `extract(url, enrich=True, cookies_from_browser=…, cookiefile=…)` · `extract_many(urls, …)`.

## 1.4 Limits

| Limit | Detail |
|-------|--------|
| Public Posts only | Private, friends-only, or age-gated Posts are out of scope |
| Sequential bulk | `extract_many` runs one URL after another. Safer against bans. Slower for large lists |
| Soft platform quotas | Anonymous clients get throttled. Symptoms are timeouts, 429s, or empty/partial HTML |
| Region / cookie variance | The same URL can render different fields by egress country or cookie state |
| Text-only Facebook | Some text Posts expose thinner media metadata than reels/videos |

## 1.5 Challenges

| Challenge | Detail |
|-----------|--------|
| Keeping extractors fresh | yt-dlp and Meta page shapes change. A green path today can break after a frontend deploy |
| Followers not always on the Post | IG / FB / Threads often need a second request to the author Profile |
| Inconsistent share semantics | Platforms invent different counters. We normalize into `shares` / `reposts` / `bookmarks` with the mapping above |
| Partial success | A Post can return `status: ok` with some null fields when the page does not show that metric |

## 1.6 Blockers

| Blocker | Why it happens | What would make it work |
|---------|----------------|-------------------------|
| Private or deleted Post | Content is not in the public HTML/API | A session that can see it (login). Out of scope |
| Instagram login wall on the Post page | Meta serves a login shell instead of media JSON for some IPs/UAs | Residential egress and/or cookies. Still fragile without login |
| Geo / copyright block | Platform returns a block page | Exit IP in an allowed region |
| yt-dlp extractor outage | Upstream site marked broken | Wait for a yt-dlp fix, or temporary cookies |

---

# 2. Comment Threads

Status: Working on YouTube, TikTok, X, Instagram, Facebook, and Threads.

Entry points: `socmeta comments <url…>` · `extract_comments()` · `extract_comments_many()`

## 2.1 Function

You give one or more Post URLs.
socmeta fetches top-level Comments (and optional nested Replies), then applies `--sort`.

```
post URL → comment list API / page → top-level Comments
        → optional Replies under each Comment
        → sort: newest | top | relevant
```

## 2.2 Metrics (per Comment)

Typical fields: `id`, `text`, `likes`, `created_at`, `username`, `display_name`, `profile_url`, `reply_count`, optional `replies[]`.

Thread-level fields: `platform`, `url`, `count`, `total` (when known), `sort`, `include_replies`, `status`, `note`.

## 2.3 Parameters

| Parameter | Default | Detail |
|-----------|---------|--------|
| URL(s) | required | One or more Post URLs |
| `--limit` | `50` | Max top-level Comments |
| `--include-replies` | off | Also fetch Replies |
| `--replies-limit` | `20` | Cap per parent when Replies are on |
| `--sort` | `newest` | `newest` · `top` (likes) · `relevant` (platform ranking when available) |
| `--ranking` | follows `--sort` | X only: force fetch mode `recency` or `likes` |

Sort behavior:

| `--sort` | Behavior |
|----------|----------|
| `newest` | By `created_at` desc. YouTube uses `comment_sort=new`. Facebook chronological intent. X fetches `recency` |
| `top` | Prefer likes. YouTube `comment_sort=top`. X likes ranking. Facebook ranked/unfiltered + client likes. Others client-side |
| `relevant` | Keep platform ranking when the fetch was already ranked. Else keep fetch order |

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
| Instagram like counts often `0` | Logged-out APIs omit diggs. `--sort top` is weak on IG |
| Instagram depth | Anonymous clients often get only a short first page (~dozens), not full threads |
| Facebook “Most relevant” | Filters spam / low quality on purpose. `total` can exceed returned rows |
| Threads reply depth | Logged-out Replies are often a single shallow page |
| X tombstones | Deleted or withheld root tweets make the conversation endpoint 404 |
| Soft rate Limits | Fast bulk comment pulls can empty out mid-batch |

## 2.6 Challenges

| Challenge | Detail |
|-----------|--------|
| Ranking vs completeness | `relevant` / Facebook ranked intents trade coverage for quality |
| Client-side Sort on capped windows | Sorting 50 fetched Comments is not “top Comments on the whole Post” |
| Keeping GraphQL `doc_id`s / FixTweet shapes current | Meta and FixTweet change without notice |
| Separating no comments from gated empty | Both can look like `count: 0`. Notes and errors try to distinguish |

## 2.7 Blockers

| Blocker | Why | What is needed |
|---------|-----|----------------|
| Instagram login for full threads | Meta gates pagination and likes behind session | Logged-in cookies. Out of scope for default socmeta |
| Facebook filtered intents | Product design, not a bug | Use `--sort newest` for broader chrono lists. Still not guaranteed complete |
| X conversation unavailable | Tweet deleted, withheld, or FixTweet outage | Different URL / wait / alternate provider |
| TikTok empty comment JSON | Challenge page or cold session | Warm video page / retry. Rarely Residential Proxy |
| Comments disabled on the Post | Creator or platform setting | Nothing to scrape |

---

# 3. Keywords / Hashtag scraper (ongoing — lives in socfeed)

Not implemented inside socmeta. Discovery is an ongoing socfeed feature.

Full detail: [socfeed → Keywords / Hashtag scraper (ongoing)](https://github.com/FadzararAI/socfeed/blob/main/docs/CAPABILITIES.md#2-keywords--hashtag-scraper-ongoing).

## 3.1 Why it is separate

Post Extract and Comment Threads take a known Post URL.
Keywords and Hashtags must find Posts first.
Those listing APIs are where platforms apply the strongest login walls and IP gates.
The work tracks in socfeed.

## 3.2 Current progress (snapshot)

| Platform | Progress | In CLI? | Blocker / next step |
|----------|----------|:-------:|---------------------|
| TikTok | Search + Hashtag built (`--sort`, `--posted`, Playwright) | Yes | Often IP-gated on datacenter exits → Residential Proxy via `--proxy` |
| YouTube | Search proven (innertube / yt-dlp; today and week filters work) | No | Wire `socfeed search --platform youtube` |
| Threads | Search proven (~20 hits, `default`/`recent`, no proxy in tests) | No | Wire CLI. No pagination by design |
| Facebook | Posts search blocked here. Hashtag / Watch explore partial | No | No solid anonymous posts search. Only approximate surfaces |
| Instagram | Not started | No | Login-walled Keyword Search |
| X | Not started | No | Login-walled search. FixTweet has no search |

## 3.3 Blockers summary

| Blocker | Platforms | Why | What is needed |
|---------|-----------|-----|----------------|
| Residential IP / anti-bot empty listings | TikTok (search and tag) | Listing XHRs return 200 with empty body even when signed | `--proxy` to residential egress |
| CLI not wired yet | YouTube, Threads | Probes succeeded. Product surface unfinished | Finish `socfeed search --platform …` |
| Anonymous posts search removed or gated | Facebook, Instagram, X | Login or empty search for logged-out clients | Session/API credentials (outside no-login scope), or weak substitutes only (FB Hashtag/Watch) |
| No deep pagination logged out | Threads (and thin FB/IG samples) | Product caps anonymous search size | Accept sample size or use official approved APIs |

## 3.4 Related socfeed sections

| Feature | Doc |
|---------|-----|
| Profile scraper | [socfeed §1](https://github.com/FadzararAI/socfeed/blob/main/docs/CAPABILITIES.md#1-profile-scraper) |
| Keywords / Hashtags (ongoing) | [socfeed §2](https://github.com/FadzararAI/socfeed/blob/main/docs/CAPABILITIES.md#2-keywords--hashtag-scraper-ongoing) |

---

## Error model

- `status: "ok"` — row produced (fields may still be null).
- `status: "fail"` — extraction stopped for that URL. See `error`.
- Bulk helpers never abort the whole list on one failure.

## License / notices

MIT — [LICENSE](../LICENSE). Third-party attributions — [NOTICE](../NOTICE).
