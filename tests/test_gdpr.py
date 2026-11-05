"""GDPR: erasure hard-deletes and recomputes the counters it touched."""
import pytest

from stapel_feed.gdpr import FeedGDPRProvider, erase_subject
from stapel_feed.models import Comment, Post, Reaction
from stapel_feed.services.counters import recount_comment, recount_post

from .factories import make_comment, make_post, make_reaction

pytestmark = pytest.mark.django_db


def test_erase_hard_deletes_and_recounts(user, other_user):
    mine = make_post(user)
    theirs = make_post(other_user)
    make_comment(mine, other_user)
    my_comment = make_comment(theirs, user)
    their_comment = make_comment(theirs, other_user)
    make_reaction("post", theirs.pk, user)
    make_reaction("post", theirs.pk, other_user)
    make_reaction("comment", their_comment.pk, user)
    make_reaction("post", mine.pk, other_user)
    recount_post(theirs)
    recount_comment(their_comment)
    assert Post.objects.get(pk=theirs.pk).comment_count == 2
    assert Post.objects.get(pk=theirs.pk).reaction_counts == {"like": 2}

    result = erase_subject("account", str(user.pk))

    assert result == {"posts": 1, "comments": 1, "reactions": 2}
    assert not Post.objects.filter(author_id=str(user.pk)).exists()
    assert not Comment.objects.filter(author_id=str(user.pk)).exists()
    assert not Reaction.objects.filter(user_id=str(user.pk)).exists()
    # Others' rows on the erased post went with it.
    assert not Reaction.objects.filter(target_type="post", target_key=str(mine.pk)).exists()
    assert not Comment.objects.filter(pk=my_comment.pk).exists()
    theirs.refresh_from_db()
    assert theirs.comment_count == 1
    assert theirs.reaction_counts == {"like": 1}
    their_comment.refresh_from_db()
    assert their_comment.reaction_counts == {}


def test_erase_is_idempotent_and_ignores_other_subjects(user):
    make_post(user)
    erase_subject("account", str(user.pk))
    assert erase_subject("account", str(user.pk)) == {"posts": 0, "comments": 0, "reactions": 0}
    assert erase_subject("workspace", str(user.pk)) is None


def test_export_has_all_three(user, other_user):
    p = make_post(user, body="mine")
    make_comment(p, user, body="c")
    make_reaction("post", p.pk, user)
    data = FeedGDPRProvider().export(str(user.pk))
    assert [x["body"] for x in data["posts"]] == ["mine"]
    assert [x["body"] for x in data["comments"]] == ["c"]
    assert [x["kind"] for x in data["reactions"]] == ["like"]


def test_owner_is_registered():
    from stapel_core.gdpr import gdpr_registry

    assert any(p.section == "feed" for p in gdpr_registry.providers)
