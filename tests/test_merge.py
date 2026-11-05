"""user.merged: everything follows the survivor; the oldest duplicate reaction wins."""
import datetime

import pytest
from django.utils import timezone
from stapel_core.comm import emit

from stapel_feed.models import Comment, Post, Reaction

from .factories import make_comment, make_post, make_reaction

pytestmark = pytest.mark.django_db


def _merge(src, dst):
    emit("user.merged", {"from_user_id": str(src.pk), "into_user_id": str(dst.pk)})


def test_posts_comments_reactions_follow(guest, user, other_user):
    p = make_post(guest)
    make_comment(make_post(other_user), guest)
    make_reaction("post", p.pk, guest)
    _merge(guest, user)
    assert Post.objects.get(pk=p.pk).author_id == str(user.pk)
    assert Comment.objects.get().author_id == str(user.pk)
    assert Reaction.objects.get().user_id == str(user.pk)


@pytest.mark.parametrize("oldest", ["guest", "account"])
def test_merged_keeps_the_oldest_duplicate_reaction(guest, user, other_user, oldest):
    p = make_post(other_user)
    g = make_reaction("post", p.pk, guest, kind="like")
    a = make_reaction("post", p.pk, user, kind="heart")
    earlier = timezone.now() - datetime.timedelta(days=1)
    Reaction.objects.filter(pk=(g if oldest == "guest" else a).pk).update(created_at=earlier)
    _merge(guest, user)
    survivor = Reaction.objects.get(target_key=str(p.pk))
    assert survivor.user_id == str(user.pk)
    assert survivor.pk == (g if oldest == "guest" else a).pk
    assert Post.objects.get(pk=p.pk).reaction_counts == {survivor.kind: 1}


def test_merge_into_self_is_a_noop(user):
    p = make_post(user)
    emit("user.merged", {"from_user_id": str(user.pk), "into_user_id": str(user.pk)})
    assert Post.objects.get(pk=p.pk).author_id == str(user.pk)
