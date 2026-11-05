"""Post services: the four reads, create, edit and delete.

Reads fan in at read time: ``home`` asks the graph once and filters posts
by author. ``home`` and ``public`` refuse with 503 when the graph cannot be
asked (an authenticated ``public`` must still hide blocked authors); one
author's page and one post degrade to public-only content instead.
"""
from __future__ import annotations

import datetime
import re

from django.db.models import QuerySet
from django.utils import timezone
from stapel_core.comm import mutate_and_emit

from ..errors import (
    ERR_400_ATTACHMENT_REF_INVALID,
    ERR_400_TOO_MANY_ATTACHMENTS,
    ERR_403_NOT_AUTHOR,
    ERR_404_POST_NOT_FOUND,
    ERR_409_EDIT_WINDOW_CLOSED,
)
from ..models import ATTACHMENT_REF_MAX_LENGTH, ContentStatus, Post, Visibility
from . import FeedError, events
from .access import can_see_post, strict_graph
from .graph import NOBODY, Graph, graph_or_unknown

#: An opaque CDN ref: ``<kind>/<hash>``.
ATTACHMENT_REF = re.compile(r"^[a-z][a-z0-9_-]{0,31}/[A-Za-z0-9][A-Za-z0-9_.-]{0,200}$")


# ── Reads ─────────────────────────────────────────────────────────────────


def _published() -> QuerySet:
    return Post.objects.filter(status=ContentStatus.PUBLISHED)


def home(viewer: str) -> QuerySet:
    """Posts of followed authors plus the viewer's own, minus blocked authors."""
    graph = strict_graph(viewer)
    authors = set(graph.following) | {viewer}
    return _published().filter(author_id__in=authors).exclude(author_id__in=graph.blocked)


def public(viewer: str | None) -> QuerySet:
    """Every public post; an authenticated viewer's blocked authors removed."""
    qs = _published().filter(visibility=Visibility.PUBLIC)
    if viewer is None:
        return qs
    graph = strict_graph(viewer)
    return qs.exclude(author_id__in=graph.blocked)


def by_author(author_id: str, viewer: str | None) -> QuerySet:
    """One author's posts; followers-only posts to followers and the author."""
    author_id = str(author_id)
    qs = _published().filter(author_id=author_id)
    if viewer == author_id:
        return qs
    graph = graph_or_unknown(viewer)
    if graph.blocks(author_id):
        return qs.none()
    if not graph.follows(author_id):
        qs = qs.filter(visibility=Visibility.PUBLIC)
    return qs


def viewer_graph(viewer: str | None) -> Graph:
    """The graph a single-object read uses: degraded, never a 503."""
    return graph_or_unknown(viewer) if viewer else NOBODY


def get_visible(post_id, viewer: str | None, graph: Graph | None = None) -> Post:
    post = Post.objects.filter(pk=post_id).first()
    if graph is None:
        graph = viewer_graph(viewer)
    if post is None or not can_see_post(post, viewer, graph):
        raise FeedError(404, ERR_404_POST_NOT_FOUND)
    return post


# ── Writes ────────────────────────────────────────────────────────────────


def clean_attachments(refs) -> list[str]:
    from ..conf import feed_settings

    refs = list(refs or [])
    limit = int(feed_settings.MAX_ATTACHMENTS)
    if len(refs) > limit:
        raise FeedError(400, ERR_400_TOO_MANY_ATTACHMENTS, {"max": limit})
    for ref in refs:
        if not isinstance(ref, str) or len(ref) > ATTACHMENT_REF_MAX_LENGTH or not ATTACHMENT_REF.match(ref):
            raise FeedError(400, ERR_400_ATTACHMENT_REF_INVALID, {"ref": str(ref)[:64]})
    return refs


def create_post(author: str, *, body: str, attachments=None, visibility=Visibility.PUBLIC) -> Post:
    refs = clean_attachments(attachments)
    with mutate_and_emit() as emit:
        post = Post.objects.create(
            author_id=author, body=body, attachments=refs, visibility=visibility,
        )
        emit(events.EVENT_POST_CREATED, events.post_created_payload(post), key=str(post.pk))
    return post


def edit_window_open(post, now: datetime.datetime | None = None) -> bool:
    from ..conf import feed_settings

    minutes = int(feed_settings.EDIT_WINDOW_MINUTES)
    if minutes <= 0:
        return False
    return (now or timezone.now()) - post.created_at <= datetime.timedelta(minutes=minutes)


def _owned_for_write(author: str, post_id) -> Post:
    post = Post.objects.select_for_update().filter(pk=post_id).first()
    if post is None or post.status == ContentStatus.DELETED:
        raise FeedError(404, ERR_404_POST_NOT_FOUND)
    if str(post.author_id) != author:
        if post.status != ContentStatus.PUBLISHED:
            raise FeedError(404, ERR_404_POST_NOT_FOUND)
        raise FeedError(403, ERR_403_NOT_AUTHOR)
    return post


def update_post(author: str, post_id, *, body=None, attachments=None) -> Post:
    from django.db import transaction

    with transaction.atomic():
        post = _owned_for_write(author, post_id)
        if post.status != ContentStatus.PUBLISHED or not edit_window_open(post):
            raise FeedError(409, ERR_409_EDIT_WINDOW_CLOSED)
        fields = ["edited_at", "updated_at"]
        if body is not None:
            post.body = body
            fields.append("body")
        if attachments is not None:
            post.attachments = clean_attachments(attachments)
            fields.append("attachments")
        post.edited_at = timezone.now()
        post.save(update_fields=fields)
    return post


def delete_post(author: str, post_id) -> None:
    """Soft delete by the author, any time; announced on the bus."""
    with mutate_and_emit() as emit:
        post = _owned_for_write(author, post_id)
        post.status = ContentStatus.DELETED
        post.save(update_fields=["status", "updated_at"])
        emit(events.EVENT_POST_DELETED, events.post_deleted_payload(post), key=str(post.pk))


def set_status(post_id, status: str) -> Post | None:
    """Staff and moderation: published <-> blocked. Deleted rows stay deleted."""
    from django.db import transaction

    with transaction.atomic():
        post = Post.objects.select_for_update().filter(pk=post_id).first()
        if post is None or post.status == ContentStatus.DELETED or post.status == status:
            return post
        post.status = status
        post.save(update_fields=["status", "updated_at"])
    return post


def published_count(author_id: str) -> int:
    return _published().filter(author_id=str(author_id)).count()


__all__ = [
    "ATTACHMENT_REF", "by_author", "clean_attachments", "create_post", "delete_post",
    "edit_window_open", "get_visible", "home", "public", "published_count", "set_status",
    "update_post", "viewer_graph",
]
