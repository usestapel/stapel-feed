"""v1 URL set for stapel-feed (plain paths, no router)."""
from typing import NamedTuple

from django.urls import path

from .views import (
    AuthorPostsView,
    CommentDetailView,
    HomeFeedView,
    PostCommentsView,
    PostDetailView,
    PostsView,
    PublicFeedView,
    ReactionsView,
)

urlpatterns = [
    path("home/", HomeFeedView.as_view(), name="feed-home"),
    path("public/", PublicFeedView.as_view(), name="feed-public"),
    path("authors/<str:user_id>/posts/", AuthorPostsView.as_view(), name="feed-author-posts"),
    path("posts/", PostsView.as_view(), name="feed-posts"),
    path("posts/<int:post_id>/", PostDetailView.as_view(), name="feed-post"),
    path("posts/<int:post_id>/comments/", PostCommentsView.as_view(), name="feed-post-comments"),
    path("comments/<int:comment_id>/", CommentDetailView.as_view(), name="feed-comment"),
    path("reactions/", ReactionsView.as_view(), name="feed-reactions"),
]


class GateEntry(NamedTuple):
    """One gated URL block: which flags gate which url patterns."""

    name: str
    flags: tuple
    patterns: tuple


#: No axis unmounts an endpoint (PUBLIC_READ and WRITE_REQUIRES_ACCOUNT are
#: behavioural), so the surface is one always-on block.
GATE_REGISTRY: dict = {
    "feed.api": GateEntry("feed.api", (), tuple(urlpatterns)),
}
