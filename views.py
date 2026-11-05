"""DRF views for stapel-feed — thin over ``services``.

Every view declares its guest stance. ``home`` is members only. Public
reads admit anyone and enforce ``PUBLIC_READ`` in the body (401 for an
unauthenticated visitor when it is off). Writes admit a guest session
statically and enforce ``WRITE_REQUIRES_ACCOUNT`` in the body.
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions
from stapel_core.django.api.errors import ERR_401_UNAUTHORIZED, StapelErrorResponse
from stapel_core.django.api.pagination import AnchorPagination
from stapel_core.django.api.permissions import (
    ANONYMOUS_ALLOWED,
    ANONYMOUS_DENIED,
)
from stapel_core.django.api.views import StapelAPIView
from stapel_core.flows import flow_step

from .flows import POST, PUBLIC_READ, REACT_COMMENT
from .presenters import get_comment_presenter, get_post_presenter
from .serializers import (
    CommentCreateRequestSerializer,
    CommentPageSerializer,
    CommentResponseSerializer,
    PostCreateRequestSerializer,
    PostPageSerializer,
    PostResponseSerializer,
    PostUpdateRequestSerializer,
    ReactionStateResponseSerializer,
    ReactionToggleRequestSerializer,
)
from .services import FeedError
from .services import comments as comment_service
from .services import posts as post_service
from .services import reactions as reaction_service
from .services.access import home_refusal, viewer_id, write_refusal

TAGS = ["Feed"]


class PostAnchorPagination(AnchorPagination):
    """Post lists, newest first, anchored on the id."""

    page_size = 20
    max_page_size = 100
    anchor_field = "id"
    anchor_type = "integer"
    ordering = "-id"


class CommentAnchorPagination(AnchorPagination):
    """Comments under a post, oldest first, anchored on the id."""

    page_size = 50
    max_page_size = 100
    anchor_field = "id"
    anchor_type = "integer"
    ordering = "id"


def _anchor_parameters(pagination) -> list:
    return [
        OpenApiParameter("anchor", int, OpenApiParameter.QUERY, required=False,
                         description="Id to continue after (exclusive)."),
        OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False,
                         description=f"Page size, default {pagination.page_size}, "
                                     f"max {pagination.max_page_size}."),
        OpenApiParameter("direction", str, OpenApiParameter.QUERY, required=False,
                         enum=["next", "prev", "center"],
                         description="Walk direction from the anchor."),
    ]


class _FeedView(StapelAPIView):
    """Renders a service refusal as the fleet error envelope."""

    def handle_exception(self, exc):
        if isinstance(exc, FeedError):
            return StapelErrorResponse(exc.status, exc.key, exc.params)
        return super().handle_exception(exc)

    def _viewer(self, request) -> str | None:
        return viewer_id(request.user)

    def _require_read(self, request) -> None:
        from .conf import feed_settings

        if not feed_settings.PUBLIC_READ and self._viewer(request) is None:
            # 401 whatever the host's authentication classes: DRF downgrades
            # NotAuthenticated to 403 when the first class sends no challenge.
            raise FeedError(401, ERR_401_UNAUTHORIZED)

    def _require_write(self, request) -> str:
        refusal = write_refusal(request.user)
        if refusal is not None:
            raise refusal
        return str(request.user.pk)

    def _post_page(self, request, qs):
        paginator = PostAnchorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        dtos = get_post_presenter()().present_many(page, self._viewer(request))
        data = PostResponseSerializer(dtos, many=True).data
        return paginator.get_paginated_response(data)

    def _post_response(self, request, post, *, status=200):
        dto = get_post_presenter()().present(post, self._viewer(request))
        return self.serialized_response(dto, status=status)


@extend_schema(tags=TAGS)
class HomeFeedView(_FeedView):
    """Posts of the people the caller follows, plus their own.

    A guest session is refused in the body (``home_requires_account``).
    """

    permission_classes = [permissions.IsAuthenticated]
    stapel_anonymous_access = ANONYMOUS_DENIED
    response_serializer_class = PostResponseSerializer

    @extend_schema(
        operation_id="feed_home_list",
        parameters=_anchor_parameters(PostAnchorPagination),
        responses={200: PostPageSerializer},
    )
    @flow_step(POST, order=3, note="Read the home feed (followed authors and own posts)")
    def get(self, request):
        refusal = home_refusal(request.user)
        if refusal is not None:
            raise refusal
        return self._post_page(request, post_service.home(self._viewer(request)))


@extend_schema(tags=TAGS)
class PublicFeedView(_FeedView):
    """Every public post, newest first."""

    permission_classes = [permissions.AllowAny]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = PostResponseSerializer

    @extend_schema(
        operation_id="feed_public_list",
        parameters=_anchor_parameters(PostAnchorPagination),
        responses={200: PostPageSerializer},
    )
    @flow_step(PUBLIC_READ, order=1, note="Read the public feed")
    def get(self, request):
        self._require_read(request)
        return self._post_page(request, post_service.public(self._viewer(request)))


@extend_schema(tags=TAGS)
class AuthorPostsView(_FeedView):
    """One author's posts; followers-only posts to their followers."""

    permission_classes = [permissions.AllowAny]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    response_serializer_class = PostResponseSerializer

    @extend_schema(
        operation_id="feed_authors_posts_list",
        parameters=_anchor_parameters(PostAnchorPagination),
        responses={200: PostPageSerializer},
    )
    @flow_step(PUBLIC_READ, order=2, note="Open one author's posts")
    def get(self, request, user_id):
        self._require_read(request)
        return self._post_page(request, post_service.by_author(user_id, self._viewer(request)))


@extend_schema(tags=TAGS)
class PostsView(_FeedView):
    """Publish a post."""

    permission_classes = [permissions.IsAuthenticated]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    request_serializer_class = PostCreateRequestSerializer
    response_serializer_class = PostResponseSerializer

    @extend_schema(
        operation_id="feed_posts_create",
        request=PostCreateRequestSerializer,
        responses={201: PostResponseSerializer},
    )
    @flow_step(POST, order=2, note="Publish a post")
    def post(self, request):
        author = self._require_write(request)
        data = self.validated_request_data(request)
        post = post_service.create_post(
            author,
            body=data["body"],
            attachments=data.get("attachments") or [],
            visibility=data.get("visibility") or "public",
        )
        return self._post_response(request, post, status=201)


@extend_schema(tags=TAGS)
class PostDetailView(_FeedView):
    """One post; the author edits it inside the window or deletes it."""

    permission_classes = [permissions.AllowAny]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    request_serializer_class = PostUpdateRequestSerializer
    response_serializer_class = PostResponseSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    @extend_schema(operation_id="feed_posts_retrieve", responses={200: PostResponseSerializer})
    @flow_step(PUBLIC_READ, order=3, note="Open one post")
    def get(self, request, post_id):
        self._require_read(request)
        return self._post_response(request, post_service.get_visible(post_id, self._viewer(request)))

    @extend_schema(
        operation_id="feed_posts_partial_update",
        request=PostUpdateRequestSerializer,
        responses={200: PostResponseSerializer},
    )
    @flow_step(POST, order=4, note="Edit the post inside the edit window")
    def patch(self, request, post_id):
        author = self._require_write(request)
        data = self.validated_request_data(request, partial=True)
        post = post_service.update_post(
            author, post_id, body=data.get("body"), attachments=data.get("attachments"),
        )
        return self._post_response(request, post)

    @extend_schema(operation_id="feed_posts_destroy", responses={204: None})
    @flow_step(POST, order=5, note="Delete the post")
    def delete(self, request, post_id):
        author = self._require_write(request)
        post_service.delete_post(author, post_id)
        return self.serialized_response(None, status=204)


@extend_schema(tags=TAGS)
class PostCommentsView(_FeedView):
    """Comments under a post: read them, add one."""

    permission_classes = [permissions.AllowAny]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    request_serializer_class = CommentCreateRequestSerializer
    response_serializer_class = CommentResponseSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    @extend_schema(
        operation_id="feed_posts_comments_list",
        parameters=_anchor_parameters(CommentAnchorPagination),
        responses={200: CommentPageSerializer},
    )
    @flow_step(REACT_COMMENT, order=1, note="Read the comments under a post")
    def get(self, request, post_id):
        self._require_read(request)
        viewer = self._viewer(request)
        qs = comment_service.for_post(post_id, viewer)
        paginator = CommentAnchorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        dtos = get_comment_presenter()().present_many(page, viewer)
        return paginator.get_paginated_response(CommentResponseSerializer(dtos, many=True).data)

    @extend_schema(
        operation_id="feed_posts_comments_create",
        request=CommentCreateRequestSerializer,
        responses={201: CommentResponseSerializer},
    )
    @flow_step(REACT_COMMENT, order=3, note="Comment on the post")
    def post(self, request, post_id):
        author = self._require_write(request)
        data = self.validated_request_data(request)
        comment = comment_service.create_comment(author, post_id, body=data["body"])
        dto = get_comment_presenter()().present(comment, author)
        return self.serialized_response(dto, status=201)


@extend_schema(tags=TAGS)
class CommentDetailView(_FeedView):
    """Delete a comment: its author or the post's author."""

    permission_classes = [permissions.IsAuthenticated]
    stapel_anonymous_access = ANONYMOUS_ALLOWED

    @extend_schema(operation_id="feed_comments_destroy", responses={204: None})
    @flow_step(REACT_COMMENT, order=4, note="Delete a comment")
    def delete(self, request, comment_id):
        user = self._require_write(request)
        comment_service.delete_comment(user, comment_id)
        return self.serialized_response(None, status=204)


@extend_schema(tags=TAGS)
class ReactionsView(_FeedView):
    """Toggle (or set) the caller's reaction on a post or a comment."""

    permission_classes = [permissions.IsAuthenticated]
    stapel_anonymous_access = ANONYMOUS_ALLOWED
    request_serializer_class = ReactionToggleRequestSerializer
    response_serializer_class = ReactionStateResponseSerializer

    @extend_schema(
        operation_id="feed_reactions_update",
        request=ReactionToggleRequestSerializer,
        responses={200: ReactionStateResponseSerializer},
    )
    @flow_step(REACT_COMMENT, order=2, note="React to the post")
    def put(self, request):
        user = self._require_write(request)
        data = self.validated_request_data(request)
        state = reaction_service.toggle(
            user, data["target_type"], data["target_key"],
            kind=data.get("kind") or "like", active=data.get("active"),
        )
        return self.serialized_response(state)
