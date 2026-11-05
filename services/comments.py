"""Comment services: list, write, delete. Flat — one level, no threads."""
from __future__ import annotations

from django.db.models import QuerySet
from stapel_core.comm import mutate_and_emit

from ..errors import ERR_403_NOT_AUTHOR, ERR_404_COMMENT_NOT_FOUND, ERR_404_POST_NOT_FOUND
from ..models import Comment, ContentStatus, Post
from . import FeedError, events
from .access import can_see_post, refuse_blocked_pair, strict_graph
from .counters import recount_post
from .posts import get_visible, viewer_graph


def for_post(post_id, viewer: str | None) -> QuerySet:
    """Published comments of a visible post, oldest first; blocked authors hidden."""
    graph = viewer_graph(viewer)
    post = get_visible(post_id, viewer, graph)
    qs = Comment.objects.filter(post=post, status=ContentStatus.PUBLISHED).select_related("post")
    if graph.blocked:
        qs = qs.exclude(author_id__in=graph.blocked)
    return qs


def create_comment(author: str, post_id, *, body: str) -> Comment:
    graph = strict_graph(author)
    with mutate_and_emit() as emit:
        post = Post.objects.select_for_update().filter(pk=post_id).first()
        if (
            post is None
            or post.status != ContentStatus.PUBLISHED
            or not can_see_post(post, author, graph)
        ):
            raise FeedError(404, ERR_404_POST_NOT_FOUND)
        refuse_blocked_pair(post.author_id, author, graph)
        comment = Comment.objects.create(post=post, author_id=author, body=body)
        recount_post(post)
        emit(
            events.EVENT_COMMENT_CREATED,
            events.comment_created_payload(comment, post),
            key=str(post.pk),
        )
    if str(post.author_id) != author:
        events.notify_after_commit(
            events.NOTIFY_COMMENT_RECEIVED,
            post.author_id,
            {
                "post_id": str(post.pk),
                "comment_id": str(comment.pk),
                "actor_id": author,
                "post_url": events.post_url(post.pk),
            },
        )
        events.activity_after_commit(post.author_id, post.pk)
    return comment


def delete_comment(user: str, comment_id) -> None:
    """Soft delete by the comment's author or the post's author."""
    from django.db import transaction

    with transaction.atomic():
        comment = Comment.objects.select_related("post").filter(pk=comment_id).first()
        if comment is None or comment.status == ContentStatus.DELETED:
            raise FeedError(404, ERR_404_COMMENT_NOT_FOUND)
        post = Post.objects.select_for_update().get(pk=comment.post_id)
        if user not in (str(comment.author_id), str(post.author_id)):
            if comment.status != ContentStatus.PUBLISHED:
                raise FeedError(404, ERR_404_COMMENT_NOT_FOUND)
            raise FeedError(403, ERR_403_NOT_AUTHOR)
        comment.status = ContentStatus.DELETED
        comment.save(update_fields=["status", "updated_at"])
        recount_post(post)


def set_status(comment_id, status: str) -> Comment | None:
    """Staff and moderation: published <-> blocked; the post's count follows."""
    from django.db import transaction

    with transaction.atomic():
        comment = Comment.objects.filter(pk=comment_id).first()
        if comment is None or comment.status in (ContentStatus.DELETED, status):
            return comment
        post = Post.objects.select_for_update().get(pk=comment.post_id)
        comment.status = status
        comment.save(update_fields=["status", "updated_at"])
        recount_post(post)
    return comment


__all__ = ["create_comment", "delete_comment", "for_post", "set_status"]
