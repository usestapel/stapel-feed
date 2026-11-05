"""Reactions: one row per user per target, toggled, counted on the target.

A toggle locks the target row, writes or removes the user's one reaction,
and recomputes the target's ``reaction_counts`` from the rows — all in one
transaction. The unique ``(target_type, target_key, user_id)`` constraint is
the backstop for two requests of one user racing: the loser's insert fails
inside a savepoint and it re-reads the winner's row.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from stapel_core.comm import mutate_and_emit

from ..errors import ERR_400_REACTION_KIND_UNKNOWN, ERR_404_COMMENT_NOT_FOUND, ERR_404_POST_NOT_FOUND
from ..models import Comment, ContentStatus, Post, Reaction, TargetType
from . import FeedError, events
from .access import can_see_post, refuse_blocked_pair, strict_graph
from .counters import recount_comment, recount_post


@dataclass(frozen=True)
class ReactionState:
    target_type: str
    target_key: str
    kind: str
    active: bool
    reaction_counts: dict


def known_kinds() -> tuple:
    from ..conf import feed_settings

    return tuple(str(k) for k in (feed_settings.REACTION_KINDS or ()))


def _lock_target(target_type: str, target_key: str, user: str, graph):
    """The locked target row, its author and its post id — or a 404."""
    if target_type == TargetType.POST:
        post = Post.objects.select_for_update().filter(pk=int(target_key)).first()
        if post is None or post.status != ContentStatus.PUBLISHED or not can_see_post(post, user, graph):
            raise FeedError(404, ERR_404_POST_NOT_FOUND)
        return post, str(post.author_id), post.pk
    comment = Comment.objects.select_for_update().select_related("post").filter(pk=int(target_key)).first()
    if (
        comment is None
        or comment.status != ContentStatus.PUBLISHED
        or comment.post.status != ContentStatus.PUBLISHED
        or not can_see_post(comment.post, user, graph)
        or graph.blocks(comment.post.author_id)
    ):
        raise FeedError(404, ERR_404_COMMENT_NOT_FOUND)
    return comment, str(comment.author_id), comment.post_id


def _existing(target_type: str, target_key: str, user: str):
    return Reaction.objects.filter(
        target_type=target_type, target_key=target_key, user_id=user
    ).first()


def _insert(target_type: str, target_key: str, user: str, kind: str) -> Reaction:
    """Insert, or adopt the row a racing request of the same user just wrote."""
    try:
        with transaction.atomic():
            return Reaction.objects.create(
                target_type=target_type, target_key=target_key, user_id=user, kind=kind,
            )
    except IntegrityError:
        row = _existing(target_type, target_key, user)
        if row is None:  # pragma: no cover - the constraint fired for a reason
            raise
        if row.kind != kind:
            row.kind = kind
            row.save(update_fields=["kind"])
        return row


def toggle(user: str, target_type: str, target_key, kind: str = "like", active=None) -> ReactionState:
    """Set or flip ``user``'s reaction ``kind`` on a target.

    ``active=None`` flips; ``True``/``False`` sets the state, so a repeat of
    the same request changes nothing. Another kind already set is replaced.
    """
    if kind not in known_kinds():
        raise FeedError(400, ERR_400_REACTION_KIND_UNKNOWN, {"kind": str(kind)[:16]})
    target_key = str(target_key)
    graph = strict_graph(user)
    with mutate_and_emit() as emit:
        target, author_id, post_id = _lock_target(target_type, target_key, user, graph)
        refuse_blocked_pair(author_id, user, graph)
        existing = _existing(target_type, target_key, user)
        has_kind = existing is not None and existing.kind == kind
        desired = (not has_kind) if active is None else bool(active)
        changed = False
        if desired and not has_kind:
            if existing is None:
                _insert(target_type, target_key, user, kind)
            else:
                existing.kind = kind
                existing.save(update_fields=["kind"])
            changed = True
        elif not desired and has_kind:
            existing.delete()
            changed = True
        if target_type == TargetType.POST:
            counts = recount_post(target).reaction_counts
        else:
            counts = recount_comment(target).reaction_counts
        if changed:
            emit(
                events.EVENT_REACTION_CHANGED,
                events.reaction_changed_payload(target_type, target_key, user, kind, desired, author_id),
                key=str(post_id),
            )
    if changed and desired and author_id != user:
        events.notify_reaction_debounced(author_id, target_type, target_key, post_id, user)
        events.activity_after_commit(author_id, post_id)
    return ReactionState(
        target_type=target_type,
        target_key=target_key,
        kind=kind,
        active=desired,
        reaction_counts=dict(counts or {}),
    )


__all__ = ["ReactionState", "known_kinds", "toggle"]
