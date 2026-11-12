"""Facts and courtesies stapel-feed sends: bus emits, notifications, signals.

Emits go through the caller's ``mutate_and_emit`` emitter (key = post id),
so the outbox row commits with the mutation. Bodies never ride the bus —
identity only. Notifications and realtime signals are best-effort and leave
only after commit.
"""
from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

EVENT_POST_CREATED = "feed.post.created"
EVENT_POST_DELETED = "feed.post.deleted"
EVENT_COMMENT_CREATED = "feed.comment.created"
EVENT_REACTION_CHANGED = "feed.reaction.changed"
SIGNAL_ACTIVITY = "feed.activity"

NOTIFY_COMMENT_RECEIVED = "feed.comment_received"
NOTIFY_REACTION_RECEIVED = "feed.reaction_received"
NOTIFY_NEW_POST_FROM_FOLLOWED = "feed.new_post_from_followed"

#: One reaction notification per target per this many seconds.
REACTION_NOTIFY_DEBOUNCE_SECONDS = 600


def post_created_payload(post) -> dict:
    return {
        "post_id": str(post.pk),
        "author_id": str(post.author_id),
        "visibility": post.visibility,
    }


def post_deleted_payload(post) -> dict:
    return {"post_id": str(post.pk), "author_id": str(post.author_id)}


def comment_created_payload(comment, post) -> dict:
    return {
        "comment_id": str(comment.pk),
        "post_id": str(post.pk),
        "author_id": str(comment.author_id),
        "post_author_id": str(post.author_id),
    }


def reaction_changed_payload(target_type, target_key, user_id, kind, added, author_id) -> dict:
    return {
        "target_type": target_type,
        "target_key": str(target_key),
        "user_id": str(user_id),
        "kind": kind,
        "added": bool(added),
        "author_id": str(author_id),
    }


def post_url(post_id) -> str:
    from ..conf import feed_settings

    template = feed_settings.POST_URL_TEMPLATE or ""
    if not template:
        return ""
    try:
        return template.format(post_id=post_id)
    except (KeyError, IndexError, ValueError):
        logger.warning("POST_URL_TEMPLATE %r cannot be formatted", template)
        return ""


def notify_after_commit(notification_type: str, user_id: str, variables: dict, *,
                        dedup_key: str | None = None, dedup_ttl: int | None = None) -> None:
    """Best-effort notification to ``user_id``, sent once the transaction commits.

    ``dedup_key``/``dedup_ttl`` go to the notifications intake, which
    delivers at most one request per ``(notification_type, dedup_key)``
    inside the window.
    """
    from ..conf import feed_settings

    if not feed_settings.NOTIFY:
        return
    dedup = {}
    if dedup_key is not None:
        dedup["dedup_key"] = dedup_key
        if dedup_ttl is not None:
            dedup["dedup_ttl"] = dedup_ttl

    def _send():
        try:
            from stapel_core.notifications.publish import request_notification

            request_notification(
                notification_type,
                user_id=str(user_id),
                variables=variables,
                source_service="feed",
                **dedup,
            )
        except Exception:
            logger.warning(
                "feed: %s notification to %s not sent", notification_type, user_id,
                exc_info=True,
            )

    transaction.on_commit(_send)


def reaction_dedup_key(target_type: str, target_key) -> str:
    return f"feed:notify:reaction:{target_type}:{target_key}"


def notify_reaction_debounced(author_id: str, target_type: str, target_key, post_id, actor_id) -> bool:
    """At most one reaction notification per target per debounce window.

    Every reaction asks; the notifications intake claims the target's
    ``dedup_key`` for ``REACTION_NOTIFY_DEBOUNCE_SECONDS`` and delivers only
    the first request in the window. Returns whether a request was made.
    """
    from ..conf import feed_settings

    if not feed_settings.NOTIFY:
        return False
    notify_after_commit(
        NOTIFY_REACTION_RECEIVED,
        author_id,
        {
            "target_type": target_type,
            "target_key": str(target_key),
            "post_id": str(post_id),
            "actor_id": str(actor_id),
            "post_url": post_url(post_id),
        },
        dedup_key=reaction_dedup_key(target_type, target_key),
        dedup_ttl=REACTION_NOTIFY_DEBOUNCE_SECONDS,
    )
    return True


def activity_after_commit(post_author_id: str, post_id) -> None:
    """Realtime hint ``feed:user:<id>`` / ``feed.activity`` (no-op without a transport)."""

    def _signal():
        from stapel_core.comm import SignalError, signal, stream_key

        try:
            signal(
                stream_key("feed", "user", str(post_author_id)),
                SIGNAL_ACTIVITY,
                {"post_id": str(post_id)},
            )
        except SignalError:
            logger.warning("feed: activity signal for user %s not addressable", post_author_id)
        except Exception:
            logger.warning("feed: activity signal for user %s failed", post_author_id, exc_info=True)

    transaction.on_commit(_signal)
