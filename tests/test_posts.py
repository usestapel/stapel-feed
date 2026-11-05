"""Create, edit, delete — the author's side of a post."""
import datetime

import pytest
from django.test import override_settings
from django.utils import timezone

from stapel_feed.models import ContentStatus, Post

from .factories import make_comment, make_post
from .helpers import V1, key

pytestmark = pytest.mark.django_db


class TestCreate:
    def test_member_posts(self, client_for, user, graph, captured_events):
        r = client_for(user).post(
            f"{V1}/posts/", {"body": "line one\nline two", "attachments": ["image/abc"]}, format="json",
        )
        assert r.status_code == 201
        body = r.json()
        assert body["body"] == "line one\nline two"
        assert body["visibility"] == "public" and body["status"] == "published"
        post = Post.objects.get(pk=body["id"])
        assert post.author_id == str(user.pk)
        created = [e for e in captured_events if e.event_type == "feed.post.created"]
        assert created and created[0].payload == {
            "post_id": str(post.pk), "author_id": str(user.pk), "visibility": "public",
        }
        assert "body" not in created[0].payload

    def test_guest_write_403_by_default(self, client_for, guest, graph):
        r = client_for(guest).post(f"{V1}/posts/", {"body": "hi"}, format="json")
        assert r.status_code == 403
        assert key(r) == "error.403.write_requires_account"

    @override_settings(STAPEL_FEED={"WRITE_REQUIRES_ACCOUNT": False})
    def test_guest_writes_when_allowed(self, client_for, guest, graph):
        assert client_for(guest).post(f"{V1}/posts/", {"body": "hi"}, format="json").status_code == 201

    def test_anonymous_cannot_post(self, api_client, db):
        assert api_client.post(f"{V1}/posts/", {"body": "hi"}, format="json").status_code in (401, 403)

    def test_body_bounds(self, client_for, user, graph):
        c = client_for(user)
        assert c.post(f"{V1}/posts/", {"body": "x" * 2001}, format="json").status_code == 400
        assert c.post(f"{V1}/posts/", {"body": ""}, format="json").status_code == 400
        assert c.post(f"{V1}/posts/", {"body": "x" * 2000}, format="json").status_code == 201

    def test_attachment_ceiling(self, client_for, user, graph):
        c = client_for(user)
        refs = [f"image/h{i}" for i in range(11)]
        r = c.post(f"{V1}/posts/", {"body": "x", "attachments": refs}, format="json")
        assert r.status_code == 400
        assert key(r) == "error.400.too_many_attachments"
        assert c.post(f"{V1}/posts/", {"body": "x", "attachments": refs[:10]}, format="json").status_code == 201

    @pytest.mark.parametrize("ref", ["https://evil.example/x.png", "noslash", "image/", "../etc/passwd"])
    def test_attachment_must_be_a_cdn_ref(self, client_for, user, graph, ref):
        r = client_for(user).post(f"{V1}/posts/", {"body": "x", "attachments": [ref]}, format="json")
        assert r.status_code == 400
        assert key(r) == "error.400.attachment_ref_invalid"


class TestEdit:
    def test_edit_inside_window(self, client_for, user, graph):
        p = make_post(user)
        r = client_for(user).patch(f"{V1}/posts/{p.pk}/", {"body": "fixed"}, format="json")
        assert r.status_code == 200
        assert r.json()["body"] == "fixed"
        assert r.json()["edited_at"] is not None

    def test_edit_outside_window_409(self, client_for, user, graph):
        p = make_post(user)
        Post.objects.filter(pk=p.pk).update(created_at=timezone.now() - datetime.timedelta(minutes=16))
        r = client_for(user).patch(f"{V1}/posts/{p.pk}/", {"body": "late"}, format="json")
        assert r.status_code == 409
        assert key(r) == "error.409.edit_window_closed"
        assert Post.objects.get(pk=p.pk).body == "hello"

    def test_edit_at_the_window_edge(self, client_for, user, graph):
        p = make_post(user)
        Post.objects.filter(pk=p.pk).update(created_at=timezone.now() - datetime.timedelta(minutes=14))
        assert client_for(user).patch(f"{V1}/posts/{p.pk}/", {"body": "ok"}, format="json").status_code == 200

    @override_settings(STAPEL_FEED={"EDIT_WINDOW_MINUTES": 0})
    def test_zero_window_means_no_edits(self, client_for, user, graph):
        p = make_post(user)
        assert client_for(user).patch(f"{V1}/posts/{p.pk}/", {"body": "x"}, format="json").status_code == 409
        assert client_for(user).get(f"{V1}/posts/{p.pk}/").json()["editable"] is False

    def test_only_the_author_edits(self, client_for, user, other_user, graph):
        p = make_post(user)
        r = client_for(other_user).patch(f"{V1}/posts/{p.pk}/", {"body": "x"}, format="json")
        assert r.status_code == 403
        assert key(r) == "error.403.not_author"

    def test_editable_flag_for_others_is_false(self, client_for, user, other_user, graph):
        p = make_post(user)
        body = client_for(other_user).get(f"{V1}/posts/{p.pk}/").json()
        assert body["editable"] is False and body["deletable"] is False


class TestDelete:
    def test_author_deletes_softly(self, client_for, api_client, user, graph, captured_events):
        p = make_post(user)
        assert client_for(user).delete(f"{V1}/posts/{p.pk}/").status_code == 204
        assert Post.objects.get(pk=p.pk).status == ContentStatus.DELETED
        assert api_client.get(f"{V1}/posts/{p.pk}/").status_code == 404
        assert [e.event_type for e in captured_events if e.event_type == "feed.post.deleted"] == ["feed.post.deleted"]

    def test_delete_decrements_the_authors_post_count(self, client_for, user, graph):
        from stapel_core.comm import call

        p = make_post(user)
        make_post(user)
        assert call("feed.counts", {"user_id": str(user.pk)}) == {"posts": 2}
        client_for(user).delete(f"{V1}/posts/{p.pk}/")
        assert call("feed.counts", {"user_id": str(user.pk)}) == {"posts": 1}

    def test_delete_after_the_edit_window_is_fine(self, client_for, user, graph):
        p = make_post(user)
        Post.objects.filter(pk=p.pk).update(created_at=timezone.now() - datetime.timedelta(days=30))
        assert client_for(user).delete(f"{V1}/posts/{p.pk}/").status_code == 204

    def test_others_cannot_delete(self, client_for, user, other_user, graph):
        p = make_post(user)
        assert client_for(other_user).delete(f"{V1}/posts/{p.pk}/").status_code == 403
        assert Post.objects.get(pk=p.pk).status == ContentStatus.PUBLISHED

    def test_deleted_post_takes_comment_route_away(self, client_for, user, other_user, graph):
        p = make_post(user)
        make_comment(p, other_user)
        client_for(user).delete(f"{V1}/posts/{p.pk}/")
        r = client_for(other_user).post(f"{V1}/posts/{p.pk}/comments/", {"body": "x"}, format="json")
        assert r.status_code == 404
