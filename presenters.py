"""Presenters for stapel-feed — the DTO-building layer (§55).

Views never instantiate a ``dto.py`` dataclass (SWAP002) nor import a
concrete presenter (SWAP001); they resolve one through ``get_presenter`` so
a host can swap the presentation via ``STAPEL_SWAP`` without forking.

A page is presented in one go: one cards call, one media call and one
reactions query for the whole page, never one per row.
"""
from __future__ import annotations

from stapel_core.django.swappable import declare_swap, get_presenter

from .dto import AuthorCardDTO, CommentDTO, PostDTO

POST_PRESENTER_KEY = "STAPEL_FEED_POST_PRESENTER"
COMMENT_PRESENTER_KEY = "STAPEL_FEED_COMMENT_PRESENTER"
DEFAULT_POST_PRESENTER = "stapel_feed.presenters.PostPresenter"
DEFAULT_COMMENT_PRESENTER = "stapel_feed.presenters.CommentPresenter"

declare_swap(POST_PRESENTER_KEY, DEFAULT_POST_PRESENTER)
declare_swap(COMMENT_PRESENTER_KEY, DEFAULT_COMMENT_PRESENTER)


def _card(cards: dict, user_id: str) -> AuthorCardDTO | None:
    card = cards.get(str(user_id))
    if card is None:
        return None
    return AuthorCardDTO(
        user_id=card["user_id"], display_name=card["display_name"], avatar=card["avatar"]
    )


def my_reactions(target_type: str, keys, viewer: str | None) -> dict:
    """``{target_key: [kind, ...]}`` of the viewer's reactions on these targets."""
    if not viewer:
        return {}
    keys = [str(k) for k in keys]
    if not keys:
        return {}
    from .models import Reaction

    mine: dict[str, list[str]] = {}
    rows = Reaction.objects.filter(
        target_type=target_type, target_key__in=keys, user_id=viewer
    ).values_list("target_key", "kind")
    for key, kind in rows:
        mine.setdefault(key, []).append(kind)
    return mine


class PostPresenter:
    """Posts -> PostDTOs for one viewer."""

    def present(self, post, viewer: str | None) -> PostDTO:
        return self.present_many([post], viewer)[0]

    def present_many(self, posts, viewer: str | None) -> list[PostDTO]:
        from .models import ContentStatus
        from .services.enrich import author_cards, image_objects
        from .services.posts import edit_window_open

        posts = list(posts)
        cards = author_cards(p.author_id for p in posts)
        images = image_objects(ref for p in posts for ref in (p.attachments or []))
        mine = my_reactions("post", [p.pk for p in posts], viewer)
        out = []
        for post in posts:
            is_author = viewer is not None and viewer == str(post.author_id)
            out.append(PostDTO(
                id=post.pk,
                author_id=str(post.author_id),
                author=_card(cards, post.author_id),
                body=post.body,
                attachments=[images[ref] for ref in (post.attachments or []) if ref in images],
                visibility=post.visibility,
                status=post.status,
                comment_count=post.comment_count,
                reaction_counts=dict(post.reaction_counts or {}),
                my_reactions=mine.get(str(post.pk), []),
                created_at=post.created_at,
                edited_at=post.edited_at,
                editable=is_author and post.status == ContentStatus.PUBLISHED and edit_window_open(post),
                deletable=is_author and post.status != ContentStatus.DELETED,
            ))
        return out


class CommentPresenter:
    """Comments -> CommentDTOs for one viewer."""

    def present(self, comment, viewer: str | None) -> CommentDTO:
        return self.present_many([comment], viewer)[0]

    def present_many(self, comments, viewer: str | None) -> list[CommentDTO]:
        from .models import ContentStatus
        from .services.enrich import author_cards

        comments = list(comments)
        cards = author_cards(c.author_id for c in comments)
        mine = my_reactions("comment", [c.pk for c in comments], viewer)
        out = []
        for comment in comments:
            post_author = str(comment.post.author_id)
            may_delete = viewer is not None and viewer in (str(comment.author_id), post_author)
            out.append(CommentDTO(
                id=comment.pk,
                post_id=comment.post_id,
                author_id=str(comment.author_id),
                author=_card(cards, comment.author_id),
                body=comment.body,
                status=comment.status,
                reaction_counts=dict(comment.reaction_counts or {}),
                my_reactions=mine.get(str(comment.pk), []),
                created_at=comment.created_at,
                deletable=may_delete and comment.status != ContentStatus.DELETED,
            ))
        return out


def get_post_presenter() -> type:
    return get_presenter(POST_PRESENTER_KEY, default=DEFAULT_POST_PRESENTER)


def get_comment_presenter() -> type:
    return get_presenter(COMMENT_PRESENTER_KEY, default=DEFAULT_COMMENT_PRESENTER)


__all__ = [
    "COMMENT_PRESENTER_KEY",
    "POST_PRESENTER_KEY",
    "CommentPresenter",
    "PostPresenter",
    "get_comment_presenter",
    "get_post_presenter",
    "my_reactions",
]
