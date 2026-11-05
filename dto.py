"""Dataclass DTOs — the API models of stapel-feed (never ORM instances).

Built only by the presenters (``presenters.py``); views never instantiate
them. Image objects are plain dicts in stapel-cdn's vocabulary
(``services.enrich.IMAGE_KEYS``).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass
class AuthorCardDTO:
    """The author as a stranger sees them (profiles' public card)."""

    user_id: str
    display_name: str
    avatar: Optional[dict]


@dataclass
class PostDTO:
    """A post as its viewer sees it."""

    id: int
    author_id: str
    author: Optional[AuthorCardDTO]
    body: str
    attachments: list[dict]
    visibility: str
    status: str
    comment_count: int
    reaction_counts: dict
    my_reactions: list[str]
    created_at: datetime.datetime
    edited_at: Optional[datetime.datetime]
    editable: bool
    deletable: bool


@dataclass
class CommentDTO:
    """A comment as its viewer sees it."""

    id: int
    post_id: int
    author_id: str
    author: Optional[AuthorCardDTO]
    body: str
    status: str
    reaction_counts: dict
    my_reactions: list[str]
    created_at: datetime.datetime
    deletable: bool

