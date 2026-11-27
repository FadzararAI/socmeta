# socmeta

socmeta reads one public Post URL for engagement metrics and optional Comment Threads. Profile Feeds and Discovery belong to socfeed.

## Language

**Post**:
One public item on a platform, addressed by a permalink URL.
_Avoid_: content piece, media object

**Post Extract**:
Reading engagement, caption, author, and related fields from a Post URL.
_Avoid_: metadata scrape, post parse

**Enrich**:
A follow-up Profile lookup that fills `followers` when the Post page did not include them.
_Avoid_: hydrate, deepen

**Comment Thread**:
Top-level Comments on a Post, with optional nested Replies.
_Avoid_: discussion dump

**Comment**:
One public reply under a Post.
_Avoid_: note, message

**Reply**:
A Comment nested under another Comment.
_Avoid_: child comment (except in API field names)

**Sort**:
Order applied to Comments: `newest`, `top`, or `relevant`.
_Avoid_: ranking (except the X `--ranking` flag)

**Discovery**:
Finding Posts by Keyword Search or Hashtag. Implemented in socfeed, not socmeta.
_Avoid_: search scrape (in socmeta docs)

**Blocker**:
A known condition that stops or weakens a feature until something outside the current design changes.
_Avoid_: challenge (unless you mean a TikTok anti-bot page)

**Limit**:
A hard or soft cap on how many rows you can get without login.
_Avoid_: constraint

**Status**:
Per-request result: `ok` when a row is produced, `fail` when that input stops with an `error`.
_Avoid_: success/error as prose synonyms for these fields
