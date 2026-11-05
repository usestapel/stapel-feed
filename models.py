"""Models of stapel-feed.

Users are referenced by ``user_id`` / ``author_id`` (``str(user.pk)``), never
a foreign key into another module. Attachments are opaque CDN refs
(``<kind>/<hash>``); what they are is stapel-cdn's business.

Counters (``comment_count``, ``reaction_counts``) are denormalized onto the
row they count and recomputed from the counted rows inside the writer's
transaction, under a row lock on the parent (``services.counters``).
"""
from __future__ import annotations

from django.db import models
from stapel_core.access import access

USER_ID_MAX_LENGTH = 64
POST_BODY_MAX_LENGTH = 2000
COMMENT_BODY_MAX_LENGTH = 1000
ATTACHMENT_REF_MAX_LENGTH = 255
REACTION_KIND_MAX_LENGTH = 16
TARGET_KEY_MAX_LENGTH = 64


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public"
    FOLLOWERS = "followers", "Followers"


class ContentStatus(models.TextChoices):
    PUBLISHED = "published", "Published"
    BLOCKED = "blocked", "Blocked"
    DELETED = "deleted", "Deleted"


@access.standard
class Post(models.Model):
    """One update by one author: plain text, a few attachments, counters."""

    author_id = models.CharField(
        max_length=USER_ID_MAX_LENGTH,
        help_text="str(user.pk) of the author.",
    )
    body = models.TextField(
        max_length=POST_BODY_MAX_LENGTH,
        help_text="Plain text; line breaks kept, no markup.",
    )
    attachments = models.JSONField(
        default=list, blank=True,
        help_text="Up to MAX_ATTACHMENTS opaque CDN refs (<kind>/<hash>).",
    )
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.PUBLIC,
        help_text="public: everyone; followers: the author's followers and the author.",
    )
    status = models.CharField(
        max_length=16, choices=ContentStatus.choices, default=ContentStatus.PUBLISHED,
        help_text="blocked by moderation, deleted by the author (soft).",
    )
    comment_count = models.PositiveIntegerField(
        default=0, help_text="Published comments; recomputed in the writer's transaction.",
    )
    reaction_counts = models.JSONField(
        default=dict, blank=True,
        help_text="{kind: n}; recomputed in the writer's transaction.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When it was posted.")
    edited_at = models.DateTimeField(
        null=True, blank=True, help_text="Last author edit; null when never edited.",
    )
    updated_at = models.DateTimeField(auto_now=True, help_text="Last write of any kind.")

    class Meta:
        app_label = "feed"
        indexes = [
            models.Index(fields=["status", "visibility", "-id"], name="feed_post_public_idx"),
            models.Index(fields=["author_id", "status", "-id"], name="feed_post_author_idx"),
        ]

    def __str__(self) -> str:
        return f"Post({self.pk}, {self.author_id})"


@access.standard
class Comment(models.Model):
    """A flat comment on a post. No threads."""

    post = models.ForeignKey(
        Post, on_delete=models.CASCADE, related_name="comments",
        help_text="The post commented on.",
    )
    author_id = models.CharField(
        max_length=USER_ID_MAX_LENGTH, db_index=True,
        help_text="str(user.pk) of the commenter.",
    )
    body = models.TextField(max_length=COMMENT_BODY_MAX_LENGTH, help_text="Plain text.")
    status = models.CharField(
        max_length=16, choices=ContentStatus.choices, default=ContentStatus.PUBLISHED,
        help_text="blocked by moderation, deleted by its author or the post author (soft).",
    )
    reaction_counts = models.JSONField(
        default=dict, blank=True,
        help_text="{kind: n}; recomputed in the writer's transaction.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When it was written.")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last write of any kind.")

    class Meta:
        app_label = "feed"
        indexes = [
            models.Index(fields=["post", "status", "id"], name="feed_comment_post_idx"),
        ]

    def __str__(self) -> str:
        return f"Comment({self.pk} on {self.post_id})"


class TargetType(models.TextChoices):
    POST = "post", "Post"
    COMMENT = "comment", "Comment"


@access.ops
class Reaction(models.Model):
    """One user's reaction on one target. Unique per (target, user)."""

    target_type = models.CharField(
        max_length=16, choices=TargetType.choices,
        help_text="post or comment.",
    )
    target_key = models.CharField(
        max_length=TARGET_KEY_MAX_LENGTH,
        help_text="The target's id as a string.",
    )
    user_id = models.CharField(
        max_length=USER_ID_MAX_LENGTH, db_index=True,
        help_text="str(user.pk) of the reacting user.",
    )
    kind = models.CharField(
        max_length=REACTION_KIND_MAX_LENGTH,
        help_text="A REACTION_KINDS entry.",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When the reaction was set.")

    class Meta:
        app_label = "feed"
        constraints = [
            models.UniqueConstraint(
                fields=["target_type", "target_key", "user_id"], name="feed_reaction_one_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["target_type", "target_key", "kind"], name="feed_reaction_target_idx"),
        ]

    def __str__(self) -> str:
        return f"Reaction({self.target_type}:{self.target_key} {self.user_id} {self.kind})"
