"""Action subscriptions of stapel-feed.

Handlers are idempotent: delivery is at-least-once.

- ``user.merged`` (stapel-auth) — a guest was folded into an account:
  posts, comments and reactions follow it; where both held a reaction on
  one target, the oldest is kept.
- ``moderation.completed`` (stapel-moderation) — the verdict on a ``post``
  or ``comment`` target: ``rejected`` hides it (status ``blocked``), an
  ``approved`` verdict on a blocked row publishes it again. Other target
  types and decisions are not ours.
- ``user.deleted`` / ``gdpr.erasure.requested`` are answered by
  ``register_gdpr_owner`` (``apps.py``), not here.
"""
import json
import logging
from pathlib import Path

from django.db import transaction
from stapel_core.comm import on_action

logger = logging.getLogger(__name__)

_CONSUMES = Path(__file__).resolve().parent / "schemas" / "consumes"

#: Moderation target types this module owns.
TARGET_POST = "post"
TARGET_COMMENT = "comment"


def _schema(name: str) -> dict:
    return json.loads((_CONSUMES / f"{name}.json").read_text(encoding="utf-8"))


def merge_users(from_user_id: str, into_user_id: str) -> dict:
    """Re-parent everything ``from_user_id`` wrote; keep the oldest duplicate reaction."""
    from .models import Comment, Post, Reaction, TargetType
    from .services.counters import recount_targets

    with transaction.atomic():
        posts = Post.objects.filter(author_id=from_user_id).update(author_id=into_user_id)
        comments = Comment.objects.filter(author_id=from_user_id).update(author_id=into_user_id)
        dropped = 0
        touched_posts, touched_comments = set(), set()
        theirs = Reaction.objects.filter(user_id=from_user_id)
        for reaction in list(theirs):
            survivor = Reaction.objects.filter(
                target_type=reaction.target_type,
                target_key=reaction.target_key,
                user_id=into_user_id,
            ).first()
            if survivor is None:
                continue
            older, newer = sorted((reaction, survivor), key=lambda r: (r.created_at, r.pk))
            newer.delete()
            dropped += 1
            if older.user_id != into_user_id:
                older.user_id = into_user_id
                older.save(update_fields=["user_id"])
            bucket = touched_posts if reaction.target_type == TargetType.POST else touched_comments
            bucket.add(int(reaction.target_key))
        moved = Reaction.objects.filter(user_id=from_user_id).update(user_id=into_user_id)
        recount_targets(touched_posts, touched_comments)
    return {"posts": posts, "comments": comments, "reactions": moved, "duplicates_dropped": dropped}


@on_action("user.merged", schema=_schema("user.merged"))
def handle_user_merged(event):
    payload = event.payload or {}
    from_user_id = str(payload.get("from_user_id") or "")
    into_user_id = str(payload.get("into_user_id") or "")
    if not from_user_id or not into_user_id:
        logger.error("user.merged without from/into user id: %s", event.event_id)
        return
    if from_user_id == into_user_id:
        return
    result = merge_users(from_user_id, into_user_id)
    if any(result.values()):
        logger.info("user.merged %s -> %s: %s", from_user_id, into_user_id, result)


@on_action("moderation.completed", schema=_schema("moderation.completed"))
def handle_moderation_completed(event):
    from .models import ContentStatus
    from .services import comments as comment_service
    from .services import posts as post_service

    payload = event.payload or {}
    target_type = payload.get("target_type")
    if target_type not in (TARGET_POST, TARGET_COMMENT):
        return
    key = str(payload.get("target_key") or "")
    decision = payload.get("decision")
    if not key.isdigit() or not decision:
        logger.warning("moderation.completed with unusable target %r: %s", key, event.event_id)
        return
    if decision == "rejected":
        status = ContentStatus.BLOCKED
    elif decision == "approved":
        status = ContentStatus.PUBLISHED
    else:
        return
    service = post_service if target_type == TARGET_POST else comment_service
    row = service.set_status(int(key), status)
    if row is None:
        logger.warning("moderation.completed for unknown %s %s", target_type, key)
        return
    logger.info("feed %s %s moderation %s -> %s", target_type, key, decision, row.status)
