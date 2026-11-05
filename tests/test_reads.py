"""The four reads: who sees what, and the 503 rule.

Named inversion tests (spec §B.7): home excludes non-followed and includes
own; a followers post is invisible to a non-follower (404 ≡ absent);
blocked authors are absent in both directions; graph unreachable → 503 for
home and public while author/detail stay 200; anonymous read 401 when
PUBLIC_READ is off.
"""
import pytest
from django.test import override_settings

from stapel_feed.models import ContentStatus, Visibility

from .factories import make_post
from .helpers import V1, ids, key

pytestmark = pytest.mark.django_db


class TestHome:
    def test_home_excludes_non_followed_and_includes_own(self, client_for, user, other_user, staff, graph):
        own = make_post(user)
        followed = make_post(other_user)
        stranger = make_post(staff)
        graph.follow(user.pk, other_user.pk)
        r = client_for(user).get(f"{V1}/home/")
        assert r.status_code == 200
        assert ids(r) == [followed.pk, own.pk]
        assert stranger.pk not in ids(r)

    def test_home_includes_followers_posts_of_followed(self, client_for, user, other_user, graph):
        p = make_post(other_user, visibility=Visibility.FOLLOWERS)
        graph.follow(user.pk, other_user.pk)
        assert ids(client_for(user).get(f"{V1}/home/")) == [p.pk]

    @pytest.mark.parametrize("direction", ["i_blocked", "they_blocked"])
    def test_blocked_author_absent_from_home(self, client_for, user, other_user, graph, direction):
        p = make_post(other_user)
        graph.follow(user.pk, other_user.pk)
        if direction == "i_blocked":
            graph.block(user.pk, other_user.pk)
        else:
            graph.block(other_user.pk, user.pk)
        assert p.pk not in ids(client_for(user).get(f"{V1}/home/"))

    def test_home_hides_deleted_and_blocked_posts(self, client_for, user, graph):
        make_post(user, status=ContentStatus.DELETED)
        make_post(user, status=ContentStatus.BLOCKED)
        assert ids(client_for(user).get(f"{V1}/home/")) == []

    def test_home_is_members_only(self, api_client, client_for, guest, graph):
        assert api_client.get(f"{V1}/home/").status_code in (401, 403)
        r = client_for(guest).get(f"{V1}/home/")
        assert r.status_code == 403
        assert key(r) == "error.403.home_requires_account"
        assert graph.calls == []

    def test_home_passes_following_max_as_limit(self, client_for, user, graph):
        with override_settings(STAPEL_FEED={"FOLLOWING_MAX": 7}):
            client_for(user).get(f"{V1}/home/")
        assert graph.calls[-1] == {"user_id": str(user.pk), "limit": 7}

    def test_truncated_graph_serves_the_first_n(self, client_for, user, other_user, staff, graph):
        """FOLLOWING_MAX=1: one followed author served, never a 500."""
        a = make_post(other_user)
        b = make_post(staff)
        graph.follow(user.pk, other_user.pk)
        graph.follow(user.pk, staff.pk)
        with override_settings(STAPEL_FEED={"FOLLOWING_MAX": 1}):
            r = client_for(user).get(f"{V1}/home/")
        assert r.status_code == 200
        assert len(set(ids(r)) & {a.pk, b.pk}) == 1


class TestPublic:
    def test_public_lists_public_posts_only(self, api_client, user, graph):
        pub = make_post(user)
        make_post(user, visibility=Visibility.FOLLOWERS)
        assert ids(api_client.get(f"{V1}/public/")) == [pub.pk]

    def test_anonymous_public_read_makes_no_graph_call(self, api_client, user, graph):
        make_post(user)
        api_client.get(f"{V1}/public/")
        assert graph.calls == []

    @pytest.mark.parametrize("direction", ["i_blocked", "they_blocked"])
    def test_blocked_author_absent_from_public(self, client_for, user, other_user, graph, direction):
        p = make_post(other_user)
        if direction == "i_blocked":
            graph.block(user.pk, other_user.pk)
        else:
            graph.block(other_user.pk, user.pk)
        r = client_for(user).get(f"{V1}/public/")
        assert r.status_code == 200
        assert p.pk not in ids(r)

    @override_settings(STAPEL_FEED={"PUBLIC_READ": False})
    def test_anonymous_read_401_when_public_read_off(self, api_client, client_for, user, graph):
        p = make_post(user)
        for path in ("/public/", f"/authors/{user.pk}/posts/", f"/posts/{p.pk}/", f"/posts/{p.pk}/comments/"):
            assert api_client.get(V1 + path).status_code == 401, path
        assert client_for(user).get(f"{V1}/public/").status_code == 200

    def test_anonymous_read_allowed_by_default(self, api_client, user, graph):
        p = make_post(user)
        assert api_client.get(f"{V1}/posts/{p.pk}/").status_code == 200


class TestGraphOutage:
    """The 503 rule: no unfiltered feed when the block check is down."""

    def test_home_and_public_answer_503(self, client_for, user, other_user, graph):
        make_post(other_user)
        graph.fail = True
        c = client_for(user)
        for path in ("/home/", "/public/"):
            r = c.get(V1 + path)
            assert r.status_code == 503, path
            assert key(r) == "error.503.social_graph_unavailable"

    def test_503_also_when_the_function_is_not_registered(self, client_for, user):
        r = client_for(user).get(f"{V1}/home/")
        assert r.status_code == 503

    def test_author_and_detail_stay_200(self, client_for, user, other_user, graph):
        pub = make_post(other_user)
        fol = make_post(other_user, visibility=Visibility.FOLLOWERS)
        graph.follow(user.pk, other_user.pk)
        graph.fail = True
        c = client_for(user)
        r = c.get(f"{V1}/authors/{other_user.pk}/posts/")
        assert r.status_code == 200
        assert ids(r) == [pub.pk]  # degraded: followers-only content withheld
        assert c.get(f"{V1}/posts/{pub.pk}/").status_code == 200
        assert c.get(f"{V1}/posts/{fol.pk}/").status_code == 404

    def test_writes_on_a_pair_answer_503(self, client_for, user, other_user, graph):
        p = make_post(other_user)
        graph.fail = True
        c = client_for(user)
        assert c.post(f"{V1}/posts/{p.pk}/comments/", {"body": "x"}, format="json").status_code == 503
        r = c.put(f"{V1}/reactions/", {"target_type": "post", "target_key": str(p.pk)}, format="json")
        assert r.status_code == 503


class TestAuthorAndDetail:
    def test_followers_post_invisible_to_non_follower(self, client_for, api_client, user, other_user, graph):
        p = make_post(other_user, visibility=Visibility.FOLLOWERS)
        r = client_for(user).get(f"{V1}/posts/{p.pk}/")
        assert r.status_code == 404
        assert key(r) == "error.404.post_not_found"
        assert api_client.get(f"{V1}/posts/{p.pk}/").status_code == 404
        assert ids(client_for(user).get(f"{V1}/authors/{other_user.pk}/posts/")) == []

    def test_followers_post_visible_to_follower_and_author(self, client_for, user, other_user, graph):
        p = make_post(other_user, visibility=Visibility.FOLLOWERS)
        graph.follow(user.pk, other_user.pk)
        assert client_for(user).get(f"{V1}/posts/{p.pk}/").status_code == 200
        assert ids(client_for(user).get(f"{V1}/authors/{other_user.pk}/posts/")) == [p.pk]
        assert client_for(other_user).get(f"{V1}/posts/{p.pk}/").status_code == 200

    def test_blocked_pair_detail_is_absent(self, client_for, user, other_user, graph):
        p = make_post(other_user)
        graph.block(other_user.pk, user.pk)
        assert client_for(user).get(f"{V1}/posts/{p.pk}/").status_code == 404
        assert ids(client_for(user).get(f"{V1}/authors/{other_user.pk}/posts/")) == []

    def test_absent_post_is_404(self, api_client, db):
        assert api_client.get(f"{V1}/posts/424242/").status_code == 404

    def test_detail_shape(self, client_for, user, graph, cards):
        cards.names[str(user.pk)] = "Alice"
        p = make_post(user, attachments=["image/abc123"])
        body = client_for(user).get(f"{V1}/posts/{p.pk}/").json()
        assert body["author"] == {"user_id": str(user.pk), "display_name": "Alice", "avatar": None}
        assert body["author_id"] == str(user.pk)
        assert body["attachments"][0]["ref"] == "image/abc123"
        assert body["attachments"][0]["meta_reason"] == "cdn_unavailable"
        assert body["editable"] is True and body["deletable"] is True
        assert body["my_reactions"] == []

    def test_cards_unreachable_renders_null_author(self, client_for, user, graph, cards):
        cards.fail = True
        p = make_post(user)
        r = client_for(user).get(f"{V1}/posts/{p.pk}/")
        assert r.status_code == 200
        assert r.json()["author"] is None

    def test_cards_are_batched_per_page(self, api_client, user, other_user, graph, cards):
        for u in (user, other_user, user):
            make_post(u)
        api_client.get(f"{V1}/public/")
        assert len(cards.calls) == 1
        assert sorted(cards.calls[0]["user_ids"]) == sorted([str(user.pk), str(other_user.pk)])

    def test_pages_are_anchored_newest_first(self, api_client, user, graph):
        posts = [make_post(user, body=f"p{i}") for i in range(3)]
        r = api_client.get(f"{V1}/public/", {"limit": 2})
        body = r.json()
        assert ids(r) == [posts[2].pk, posts[1].pk]
        assert body["has_next"] is True
        r2 = api_client.get(f"{V1}/public/", {"limit": 2, "anchor": body["next_anchor"]})
        assert ids(r2) == [posts[0].pk]
