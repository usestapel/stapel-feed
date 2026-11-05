"""Denormalized counters, recomputed from the rows they count.

Every writer that changes what a counter counts calls :func:`recount_post` /
:func:`recount_comment` inside its own transaction, AFTER taking the parent
row with ``select_for_update``. Recomputing (rather than ``+= 1`` on a value
read earlier) is what keeps two interleaved writers from losing an update:
whichever commits second counts the first one's row too.
"""
from __future__ import annotations

from django.db.models import Count

from ..models import Comment, ContentStatus, Post, Reaction, TargetType


def reaction_counts(target_type: str, target_key) -> dict:
    rows = (
        Reaction.objects.filter(target_type=target_type, target_key=str(target_key))
        .values("kind")
        .annotate(n=Count("id"))
        .order_by("kind")
    )
    return {row["kind"]: row["n"] for row in rows if row["n"]}


def recount_post(post: Post) -> Post:
    post.comment_count = Comment.objects.filter(
        post_id=post.pk, status=ContentStatus.PUBLISHED
    ).count()
    post.reaction_counts = reaction_counts(TargetType.POST, post.pk)
    post.save(update_fields=["comment_count", "reaction_counts", "updated_at"])
    return post


def recount_comment(comment: Comment) -> Comment:
    comment.reaction_counts = reaction_counts(TargetType.COMMENT, comment.pk)
    comment.save(update_fields=["reaction_counts", "updated_at"])
    return comment


def recount_targets(post_ids=(), comment_ids=()) -> None:
    """Recount many targets (GDPR erasure, merges), each under its row lock."""
    for post in Post.objects.select_for_update().filter(pk__in=set(post_ids)).order_by("pk"):
        recount_post(post)
    for comment in Comment.objects.select_for_update().filter(pk__in=set(comment_ids)).order_by("pk"):
        recount_comment(comment)


__all__ = ["reaction_counts", "recount_comment", "recount_post", "recount_targets"]
