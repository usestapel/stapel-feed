"""GDPR for stapel-feed — erasure is a hard delete.

A feed keeps no economics, so erasing an ``account`` deletes everything the
person wrote — posts (their comments and reactions by others go with them),
comments and reactions — and recomputes the counters of every surviving
post or comment the person had commented on or reacted to.

One operation, :func:`erase_subject`, reached by the in-process provider and
by ``register_gdpr_owner``'s ``gdpr.erasure.requested`` / ``user.deleted``
subscribers alike.
"""
from __future__ import annotations

from stapel_core.gdpr import GDPRProvider


class FeedGDPRProvider(GDPRProvider):
    section = "feed"

    def export(self, user_id) -> dict:
        from .models import Comment, Post, Reaction

        user_id = str(user_id)
        return {
            "posts": [
                {
                    "id": post.pk,
                    "body": post.body,
                    "attachments": list(post.attachments or []),
                    "visibility": post.visibility,
                    "status": post.status,
                    "created_at": post.created_at.isoformat(),
                    "edited_at": post.edited_at.isoformat() if post.edited_at else None,
                }
                for post in Post.objects.filter(author_id=user_id).order_by("id")
            ],
            "comments": [
                {
                    "id": comment.pk,
                    "post_id": comment.post_id,
                    "body": comment.body,
                    "status": comment.status,
                    "created_at": comment.created_at.isoformat(),
                }
                for comment in Comment.objects.filter(author_id=user_id).order_by("id")
            ],
            "reactions": [
                {
                    "target_type": reaction.target_type,
                    "target_key": reaction.target_key,
                    "kind": reaction.kind,
                    "created_at": reaction.created_at.isoformat(),
                }
                for reaction in Reaction.objects.filter(user_id=user_id).order_by("id")
            ],
        }

    def delete(self, user_id) -> None:
        erase_subject("account", user_id)

    anonymize = delete


OWNER = FeedGDPRProvider.section
SUBJECT_TYPES = ("account",)


def erase_subject(subject_type, subject_key, workspace_id=None):
    """Hard-delete one account's posts, comments and reactions. Idempotent."""
    from django.db import transaction

    from .models import Comment, Post, Reaction, TargetType
    from .services.counters import recount_targets

    if subject_type != "account" or not subject_key:
        return None
    user_id = str(subject_key)
    with transaction.atomic():
        own_posts = list(Post.objects.filter(author_id=user_id).values_list("pk", flat=True))
        own_comments = set(
            Comment.objects.filter(author_id=user_id).values_list("pk", flat=True)
        )
        dead_comments = set(
            Comment.objects.filter(post_id__in=own_posts).values_list("pk", flat=True)
        ) | own_comments

        mine = Reaction.objects.filter(user_id=user_id)
        touched_posts = {
            int(k) for k in mine.filter(target_type=TargetType.POST).values_list("target_key", flat=True)
        }
        touched_comments = {
            int(k) for k in mine.filter(target_type=TargetType.COMMENT).values_list("target_key", flat=True)
        }
        touched_posts |= set(
            Comment.objects.filter(pk__in=own_comments).values_list("post_id", flat=True)
        )

        reactions, _ = mine.delete()
        # Reactions of others on rows that are about to disappear.
        Reaction.objects.filter(
            target_type=TargetType.POST, target_key__in=[str(p) for p in own_posts]
        ).delete()
        Reaction.objects.filter(
            target_type=TargetType.COMMENT, target_key__in=[str(c) for c in dead_comments]
        ).delete()
        Comment.objects.filter(pk__in=own_comments).delete()
        Post.objects.filter(pk__in=own_posts).delete()

        recount_targets(touched_posts - set(own_posts), touched_comments - dead_comments)
    return {"posts": len(own_posts), "comments": len(own_comments), "reactions": reactions}
