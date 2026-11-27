"""Comment sort modes: newest / top / relevant."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

CommentSort = Literal["newest", "top", "relevant"]

SORT_CHOICES = ("newest", "top", "relevant")


def normalize_sort(value: str | None) -> CommentSort:
    if not value:
        return "newest"
    v = str(value).strip().lower()
    aliases = {
        "new": "newest",
        "recent": "newest",
        "recency": "newest",
        "latest": "newest",
        "top": "top",
        "likes": "top",
        "best": "top",
        "relevant": "relevant",
        "relevance": "relevant",
        "ranked": "relevant",
    }
    out = aliases.get(v, v)
    if out not in SORT_CHOICES:
        return "newest"
    return out  # type: ignore[return-value]


def _ts_key(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    if text.isdigit():
        return float(text)
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def _likes_key(comment: dict[str, Any]) -> float:
    likes = comment.get("likes")
    if likes is None:
        likes = comment.get("like_count")
    try:
        return float(likes or 0)
    except (TypeError, ValueError):
        return 0.0


def _sort_list(comments: list[Any], sort: CommentSort) -> None:
    if sort == "relevant":
        # Preserve platform/API order (already relevance-ranked when fetched that way).
        return
    if sort == "top":
        comments.sort(key=lambda c: (_likes_key(c or {}), _ts_key((c or {}).get("created_at"))), reverse=True)
        return
    # newest
    comments.sort(key=lambda c: _ts_key((c or {}).get("created_at")), reverse=True)


def apply_comment_sort(result: dict[str, Any], sort: CommentSort = "newest") -> dict[str, Any]:
    """Apply ``sort`` to top-level comments and nested replies."""
    sort = normalize_sort(sort)
    comments = result.get("comments")
    if not isinstance(comments, list):
        result["sort"] = sort
        return result

    _sort_list(comments, sort)
    for c in comments:
        if not isinstance(c, dict):
            continue
        replies = c.get("replies")
        if isinstance(replies, list):
            _sort_list(replies, sort)

    result["comments"] = comments
    result["sort"] = sort

    labels = {
        "newest": "newest → oldest",
        "top": "top (by likes)",
        "relevant": "relevant (platform ranking)",
    }
    label = labels[sort]
    note = result.get("note")
    if isinstance(note, str) and note.strip():
        # Replace prior sort phrases if present, else append.
        base = note
        for phrase in (
            "Sorted newest → oldest.",
            "newest → oldest.",
            "Sorted newest → oldest",
        ):
            base = base.replace(phrase, "").strip()
        base = base.rstrip(".")
        result["note"] = f"{base}. Sorted {label}." if base else f"Sorted {label}."
    else:
        result["note"] = f"Sorted {label}."
    return result


# Back-compat alias
def sort_comments_newest_first(result: dict[str, Any]) -> dict[str, Any]:
    return apply_comment_sort(result, "newest")
