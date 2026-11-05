"""Comments: flat, counted on the post, notified to the post author."""
import pytest

from stapel_feed.models import Comment, ContentStatus, Post, Visibility

from .factories import make_comment, make_post
from .helpers import V1, ids, key

pytestmark = pytest.mark.django_db


@pytest.fixture
def notified(monkeypatch):
    sent = []

    def fake(notification_type, user_id=None, variables=None, **kwargs):
        sent.append((notification_type, user_id, variables))
        return True

    monkeypatch.setattr("stapel_core.notifications.publish.request_notification", fake)
    return sent


def test_comment_counts_and_announces(client_for, user, other_user, graph, captured_events,
                                      notified, django_capture_on_commit_callbacks):
    p = make_post(user)
    with django_capture_on_commit_callbacks(execute=True):
        r = client_for(other_user).post(f"{V1}/posts/{p.pk}/comments/", {"body": "nice"}, format="json")
    assert r.status_code == 201
    body = r.json()
    assert body["post_id"] == p.pk and body["deletable"] is True
    assert Post.objects.get(pk=p.pk).comment_count == 1
    events = [e.payload for e in captured_events if e.event_type == "feed.comment.created"]
    assert events == [{
        "comment_id": str(body["id"]), "post_id": str(p.pk),
        "author_id": str(other_user.pk), "post_author_id": str(user.pk),
    }]
    assert [(t, u) for t, u, _ in notified] == [("feed.comment_received", str(user.pk))]


def test_own_comment_is_not_notified(client_for, user, graph, notified, django_capture_on_commit_callbacks):
    p = make_post(user)
    with django_capture_on_commit_callbacks(execute=True):
        client_for(user).post(f"{V1}/posts/{p.pk}/comments/", {"body": "me"}, format="json")
    assert notified == []


def test_comments_list_oldest_first(api_client, user, other_user, graph):
    p = make_post(user)
    a = make_comment(p, other_user)
    b = make_comment(p, user)
    make_comment(p, user, status=ContentStatus.DELETED)
    assert ids(api_client.get(f"{V1}/posts/{p.pk}/comments/")) == [a.pk, b.pk]


def test_comments_of_a_hidden_post_are_absent(client_for, user, other_user, graph):
    p = make_post(other_user, visibility=Visibility.FOLLOWERS)
    make_comment(p, other_user)
    assert client_for(user).get(f"{V1}/posts/{p.pk}/comments/").status_code == 404


def test_comment_on_blocked_or_deleted_post_is_404(client_for, user, other_user, graph):
    for status in (ContentStatus.BLOCKED, ContentStatus.DELETED):
        p = make_post(other_user, status=status)
        r = client_for(user).post(f"{V1}/posts/{p.pk}/comments/", {"body": "x"}, format="json")
        assert r.status_code == 404
        assert key(r) == "error.404.post_not_found"


def test_comment_on_a_blocked_pair_is_hidden(client_for, user, other_user, graph):
    """A block hides the post, so the write answers like an absent post."""
    p = make_post(other_user)
    graph.block(other_user.pk, user.pk)
    r = client_for(user).post(f"{V1}/posts/{p.pk}/comments/", {"body": "x"}, format="json")
    assert r.status_code == 404
    assert Comment.objects.count() == 0


def test_guest_comment_403(client_for, user, guest, graph):
    p = make_post(user)
    r = client_for(guest).post(f"{V1}/posts/{p.pk}/comments/", {"body": "x"}, format="json")
    assert r.status_code == 403
    assert key(r) == "error.403.write_requires_account"


def test_comment_body_bound(client_for, user, graph):
    p = make_post(user)
    assert client_for(user).post(
        f"{V1}/posts/{p.pk}/comments/", {"body": "x" * 1001}, format="json"
    ).status_code == 400


class TestDelete:
    def test_delete_decrements_the_post_count(self, client_for, user, other_user, graph):
        p = make_post(user)
        c = client_for(other_user)
        cid = c.post(f"{V1}/posts/{p.pk}/comments/", {"body": "x"}, format="json").json()["id"]
        c.post(f"{V1}/posts/{p.pk}/comments/", {"body": "y"}, format="json")
        assert Post.objects.get(pk=p.pk).comment_count == 2
        assert c.delete(f"{V1}/comments/{cid}/").status_code == 204
        assert Post.objects.get(pk=p.pk).comment_count == 1
        assert Comment.objects.get(pk=cid).status == ContentStatus.DELETED

    def test_post_author_may_delete(self, client_for, user, other_user, graph):
        p = make_post(user)
        cm = make_comment(p, other_user)
        assert client_for(user).delete(f"{V1}/comments/{cm.pk}/").status_code == 204

    def test_stranger_may_not_delete(self, client_for, user, other_user, staff, graph):
        p = make_post(user)
        cm = make_comment(p, other_user)
        r = client_for(staff).delete(f"{V1}/comments/{cm.pk}/")
        assert r.status_code == 403
        assert key(r) == "error.403.not_author"

    def test_absent_comment_404(self, client_for, user, graph):
        r = client_for(user).delete(f"{V1}/comments/999/")
        assert r.status_code == 404
        assert key(r) == "error.404.comment_not_found"
