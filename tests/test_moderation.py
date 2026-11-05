"""The takedown: a rejecting verdict hides from every read; the author sees `blocked`."""
import uuid

import pytest
from stapel_core.comm import call, emit

from stapel_feed.models import Comment, ContentStatus, Post

from .factories import make_comment, make_post
from .helpers import V1, ids

pytestmark = pytest.mark.django_db


def _verdict(target_type, target_key, decision):
    emit("moderation.completed", {
        "case_id": str(uuid.uuid4()), "target_type": target_type,
        "target_key": str(target_key), "decision": decision,
    })


def test_rejected_post_hides_from_every_read(api_client, client_for, user, other_user, graph):
    p = make_post(user)
    graph.follow(other_user.pk, user.pk)
    _verdict("post", p.pk, "rejected")
    assert Post.objects.get(pk=p.pk).status == ContentStatus.BLOCKED
    viewer = client_for(other_user)
    assert p.pk not in ids(viewer.get(f"{V1}/home/"))
    assert p.pk not in ids(viewer.get(f"{V1}/public/"))
    assert p.pk not in ids(api_client.get(f"{V1}/public/"))
    assert ids(viewer.get(f"{V1}/authors/{user.pk}/posts/")) == []
    assert viewer.get(f"{V1}/posts/{p.pk}/").status_code == 404
    assert viewer.get(f"{V1}/posts/{p.pk}/comments/").status_code == 404
    own = client_for(user).get(f"{V1}/posts/{p.pk}/")
    assert own.status_code == 200
    assert own.json()["status"] == "blocked"
    assert own.json()["editable"] is False


def test_approved_verdict_republishes(user, graph):
    p = make_post(user, status=ContentStatus.BLOCKED)
    _verdict("post", p.pk, "approved")
    assert Post.objects.get(pk=p.pk).status == ContentStatus.PUBLISHED


def test_dismissed_and_needs_review_change_nothing(user, graph):
    p = make_post(user)
    for decision in ("dismissed", "needs_review"):
        _verdict("post", p.pk, decision)
    assert Post.objects.get(pk=p.pk).status == ContentStatus.PUBLISHED


def test_other_target_types_are_ignored(user, graph):
    p = make_post(user)
    _verdict("listing", p.pk, "rejected")
    assert Post.objects.get(pk=p.pk).status == ContentStatus.PUBLISHED


def test_deleted_post_stays_deleted(user, graph):
    p = make_post(user, status=ContentStatus.DELETED)
    _verdict("post", p.pk, "approved")
    assert Post.objects.get(pk=p.pk).status == ContentStatus.DELETED


def test_rejected_comment_leaves_the_count(api_client, user, other_user, graph):
    p = make_post(user)
    cm = make_comment(p, other_user)
    from stapel_feed.services.counters import recount_post

    recount_post(p)
    _verdict("comment", cm.pk, "rejected")
    assert Comment.objects.get(pk=cm.pk).status == ContentStatus.BLOCKED
    assert Post.objects.get(pk=p.pk).comment_count == 0
    assert ids(api_client.get(f"{V1}/posts/{p.pk}/comments/")) == []


class TestContentFunction:
    def test_post_content(self, user, graph):
        p = make_post(user, body="hi", attachments=["image/a1"])
        answer = call("feed.moderation_content", {"post_id": str(p.pk)})
        assert answer["author_id"] == str(user.pk)
        assert answer["text"] == answer["body"] == "hi"
        assert answer["media"] == answer["attachments"] == ["image/a1"]

    def test_bare_target_key_names_a_post(self, user, graph):
        p = make_post(user)
        assert call("feed.moderation_content", {"target_key": str(p.pk)})["author_id"] == str(user.pk)

    def test_comment_content(self, user, other_user, graph):
        cm = make_comment(make_post(user), other_user, body="rude")
        answer = call("feed.moderation_content", {"comment_id": str(cm.pk)})
        assert answer["author_id"] == str(other_user.pk)
        assert answer["text"] == "rude"

    @pytest.mark.parametrize("payload", [{"post_id": "999"}, {"comment_id": "999"}, {"post_id": "abc"}])
    def test_absent_target_raises_lookup(self, db, payload):
        from stapel_core.comm import CommError

        with pytest.raises((LookupError, CommError)) as info:
            call("feed.moderation_content", payload)
        cause = info.value if isinstance(info.value, LookupError) else info.value.__cause__
        assert isinstance(cause, LookupError)
