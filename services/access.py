"""Who may see and write what — one place, used by every read and write.

Hidden is absent: a post a viewer may not see answers the same 404 as one
that does not exist (a blocked pair, a followers-only post to a stranger,
a post moderation took down — except to its author).
"""
from __future__ import annotations

from types import SimpleNamespace

from ..errors import (
    ERR_403_BLOCKED,
    ERR_403_HOME_REQUIRES_ACCOUNT,
    ERR_403_WRITE_REQUIRES_ACCOUNT,
    ERR_503_SOCIAL_GRAPH_UNAVAILABLE,
)
from ..models import ContentStatus, Visibility
from . import FeedError
from .graph import Graph, GraphUnavailable, fetch_graph


def viewer_id(user) -> str | None:
    """``str(user.pk)`` for an authenticated user (a guest row too), else None."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return str(user.pk)


def _has_account(user) -> bool:
    from stapel_core.django.api.permissions import IsNotAnonymousUser

    return IsNotAnonymousUser().has_permission(SimpleNamespace(user=user), None)


def home_refusal(user) -> FeedError | None:
    """``home/`` is members only: a guest session follows nobody."""
    return None if _has_account(user) else FeedError(403, ERR_403_HOME_REQUIRES_ACCOUNT)


def write_refusal(user) -> FeedError | None:
    """The guest wall: core's predicate, this module's switch and error key."""
    from ..conf import feed_settings

    if not feed_settings.WRITE_REQUIRES_ACCOUNT:
        return None
    if _has_account(user):
        return None
    return FeedError(403, ERR_403_WRITE_REQUIRES_ACCOUNT)


def strict_graph(user_id: str) -> Graph:
    """The graph or a 503 — for surfaces that must not forget a block."""
    try:
        return fetch_graph(user_id)
    except GraphUnavailable as exc:
        raise FeedError(503, ERR_503_SOCIAL_GRAPH_UNAVAILABLE) from exc


def can_see_post(post, viewer: str | None, graph: Graph) -> bool:
    author = str(post.author_id)
    is_author = viewer is not None and viewer == author
    if post.status == ContentStatus.DELETED:
        return False
    if post.status == ContentStatus.BLOCKED and not is_author:
        return False
    if not is_author and graph.blocks(author):
        return False
    if post.visibility == Visibility.FOLLOWERS and not (is_author or graph.follows(author)):
        return False
    return True


def refuse_blocked_pair(other_user_id: str, me: str, graph: Graph) -> None:
    if str(other_user_id) != me and graph.blocks(other_user_id):
        raise FeedError(403, ERR_403_BLOCKED)


__all__ = ["can_see_post", "home_refusal", "refuse_blocked_pair", "strict_graph", "viewer_id", "write_refusal"]
