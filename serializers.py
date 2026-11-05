"""Serializers for the stapel-feed API.

The class names are the codegen contract: drf-spectacular names each
component after its serializer minus the ``Serializer`` suffix
(``PostResponse``, ``PostPage``, …), and the frontend pair generates its
client from those names. Every CharField declares a ``max_length``.
"""
from rest_framework import serializers

from . import models as m

IMAGE_META_STATUSES = ("ok", "partial", "missing")


class ImageObjectSerializer(serializers.Serializer):
    """The fleet's one image object (stapel-cdn's describe vocabulary)."""

    ref = serializers.CharField(max_length=m.ATTACHMENT_REF_MAX_LENGTH)
    mime = serializers.CharField(max_length=100, allow_null=True)
    ext = serializers.CharField(max_length=16, allow_null=True)
    bytes = serializers.IntegerField(allow_null=True)
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)
    aspect = serializers.FloatField(allow_null=True)
    square = serializers.BooleanField(allow_null=True)
    animated = serializers.BooleanField(allow_null=True)
    preview_b64 = serializers.CharField(max_length=16384, allow_null=True)
    preview_kind = serializers.CharField(max_length=32, allow_null=True)
    variants = serializers.ListField(child=serializers.DictField())
    meta_status = serializers.ChoiceField(choices=IMAGE_META_STATUSES)
    meta_reason = serializers.CharField(max_length=64, allow_null=True)


class AuthorCardSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=m.USER_ID_MAX_LENGTH)
    display_name = serializers.CharField(max_length=255, allow_blank=True)
    avatar = ImageObjectSerializer(allow_null=True)


def _counts():
    return serializers.DictField(child=serializers.IntegerField(min_value=0))


def _kinds():
    return serializers.ListField(child=serializers.CharField(max_length=m.REACTION_KIND_MAX_LENGTH))


# ── Posts ─────────────────────────────────────────────────────────────────


class PostResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    author_id = serializers.CharField(max_length=m.USER_ID_MAX_LENGTH)
    author = AuthorCardSerializer(allow_null=True)
    body = serializers.CharField(max_length=m.POST_BODY_MAX_LENGTH)
    attachments = ImageObjectSerializer(many=True)
    visibility = serializers.ChoiceField(choices=m.Visibility.choices)
    status = serializers.ChoiceField(choices=m.ContentStatus.choices)
    comment_count = serializers.IntegerField(min_value=0)
    reaction_counts = _counts()
    my_reactions = _kinds()
    created_at = serializers.DateTimeField()
    edited_at = serializers.DateTimeField(allow_null=True)
    editable = serializers.BooleanField()
    deletable = serializers.BooleanField()


class PostPageSerializer(serializers.Serializer):
    """The AnchorPagination envelope of every post list (schema only —
    the view's paginator builds the body)."""

    items = PostResponseSerializer(many=True)
    next_anchor = serializers.IntegerField(allow_null=True)
    prev_anchor = serializers.IntegerField(allow_null=True)
    has_next = serializers.BooleanField()
    has_prev = serializers.BooleanField()
    count = serializers.IntegerField()


class PostCreateRequestSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=m.POST_BODY_MAX_LENGTH)
    # MAX_ATTACHMENTS and the ref shape are enforced by the service (the
    # ceiling is a setting); the wire bound is the column's.
    attachments = serializers.ListField(
        child=serializers.CharField(max_length=m.ATTACHMENT_REF_MAX_LENGTH),
        required=False, default=list, max_length=100,
    )
    visibility = serializers.ChoiceField(
        choices=m.Visibility.choices, required=False, default=m.Visibility.PUBLIC
    )


class PostUpdateRequestSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=m.POST_BODY_MAX_LENGTH, required=False)
    attachments = serializers.ListField(
        child=serializers.CharField(max_length=m.ATTACHMENT_REF_MAX_LENGTH),
        required=False, max_length=100,
    )


# ── Comments ──────────────────────────────────────────────────────────────


class CommentResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    post_id = serializers.IntegerField()
    author_id = serializers.CharField(max_length=m.USER_ID_MAX_LENGTH)
    author = AuthorCardSerializer(allow_null=True)
    body = serializers.CharField(max_length=m.COMMENT_BODY_MAX_LENGTH)
    status = serializers.ChoiceField(choices=m.ContentStatus.choices)
    reaction_counts = _counts()
    my_reactions = _kinds()
    created_at = serializers.DateTimeField()
    deletable = serializers.BooleanField()


class CommentPageSerializer(serializers.Serializer):
    """The AnchorPagination envelope of ``GET posts/<id>/comments/``."""

    items = CommentResponseSerializer(many=True)
    next_anchor = serializers.IntegerField(allow_null=True)
    prev_anchor = serializers.IntegerField(allow_null=True)
    has_next = serializers.BooleanField()
    has_prev = serializers.BooleanField()
    count = serializers.IntegerField()


class CommentCreateRequestSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=m.COMMENT_BODY_MAX_LENGTH)


# ── Reactions ─────────────────────────────────────────────────────────────


class ReactionToggleRequestSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=m.TargetType.choices)
    target_key = serializers.RegexField(r"^[0-9]{1,19}$", max_length=m.TARGET_KEY_MAX_LENGTH)
    kind = serializers.CharField(
        max_length=m.REACTION_KIND_MAX_LENGTH, required=False, default="like"
    )
    # Absent: toggle. Present: the desired state, so a repeat is a no-op.
    active = serializers.BooleanField(required=False, allow_null=True, default=None)


class ReactionStateResponseSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=m.TargetType.choices)
    target_key = serializers.CharField(max_length=m.TARGET_KEY_MAX_LENGTH)
    kind = serializers.CharField(max_length=m.REACTION_KIND_MAX_LENGTH)
    active = serializers.BooleanField()
    reaction_counts = _counts()
