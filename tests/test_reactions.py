"""Reactions: one per user per target, toggled, counted in the same transaction."""
import pytest
from django.test import override_settings

from stapel_feed.models import Comment, Post, Reaction
from stapel_feed.services import reactions as reaction_service

from .factories import make_comment, make_post
from .helpers import V1, key

pytestmark = pytest.mark.django_db


def _put(client, target_key, target_type="post", **extra):
    return client.put(
        f"{V1}/reactions/",
        {"target_type": target_type, "target_key": str(target_key), **extra},
        format="json",
    )


def test_toggle_on_and_off(client_for, user, other_user, graph, captured_events):
    p = make_post(user)
    c = client_for(other_user)
    r = _put(c, p.pk)
    assert r.status_code == 200
    assert r.json() == {"target_type": "post", "target_key": str(p.pk), "kind": "like",
                        "active": True, "reaction_counts": {"like": 1}}
    assert Post.objects.get(pk=p.pk).reaction_counts == {"like": 1}
    assert c.get(f"{V1}/posts/{p.pk}/").json()["my_reactions"] == ["like"]
    r = _put(c, p.pk)
    assert r.json()["active"] is False and r.json()["reaction_counts"] == {}
    assert Post.objects.get(pk=p.pk).reaction_counts == {}
    changes = [e.payload["added"] for e in captured_events if e.event_type == "feed.reaction.changed"]
    assert changes == [True, False]


def test_setting_the_same_state_twice_is_idempotent(client_for, user, other_user, graph, captured_events):
    p = make_post(user)
    c = client_for(other_user)
    for _ in range(2):
        r = _put(c, p.pk, active=True)
        assert r.json()["active"] is True
    assert Reaction.objects.count() == 1
    assert Post.objects.get(pk=p.pk).reaction_counts == {"like": 1}
    assert len([e for e in captured_events if e.event_type == "feed.reaction.changed"]) == 1
    _put(c, p.pk, active=False)
    _put(c, p.pk, active=False)
    assert Reaction.objects.count() == 0


@override_settings(STAPEL_FEED={"REACTION_KINDS": ("like", "heart")})
def test_another_kind_replaces_the_first(client_for, user, other_user, graph):
    p = make_post(user)
    c = client_for(other_user)
    _put(c, p.pk, kind="like")
    r = _put(c, p.pk, kind="heart")
    assert r.json()["reaction_counts"] == {"heart": 1}
    assert Reaction.objects.get().kind == "heart"


def test_unknown_kind_400(client_for, user, other_user, graph):
    p = make_post(user)
    r = _put(client_for(other_user), p.pk, kind="heart")
    assert r.status_code == 400
    assert key(r) == "error.400.reaction_kind_unknown"
    assert Reaction.objects.count() == 0


def test_comment_reaction_counts_on_the_comment(client_for, user, other_user, graph):
    p = make_post(user)
    cm = make_comment(p, user)
    r = _put(client_for(other_user), cm.pk, target_type="comment")
    assert r.status_code == 200
    assert Comment.objects.get(pk=cm.pk).reaction_counts == {"like": 1}
    assert Post.objects.get(pk=p.pk).reaction_counts == {}


def test_hidden_target_is_404(client_for, user, other_user, graph):
    from stapel_feed.models import ContentStatus

    p = make_post(user, status=ContentStatus.BLOCKED)
    assert _put(client_for(other_user), p.pk).status_code == 404
    assert _put(client_for(other_user), 9999, target_type="comment").status_code == 404


def test_blocked_pair_cannot_react(client_for, user, other_user, graph):
    p = make_post(user)
    graph.block(user.pk, other_user.pk)
    assert _put(client_for(other_user), p.pk).status_code == 404
    assert Reaction.objects.count() == 0


def test_blocked_comment_author_answers_403(client_for, user, other_user, staff, graph):
    """The post is visible, the comment's author blocked the reactor."""
    p = make_post(user)
    cm = make_comment(p, staff)
    graph.block(staff.pk, other_user.pk)
    r = _put(client_for(other_user), cm.pk, target_type="comment")
    assert r.status_code == 403
    assert key(r) == "error.403.blocked"


def test_guest_reaction_403(client_for, user, guest, graph):
    p = make_post(user)
    r = _put(client_for(guest), p.pk)
    assert r.status_code == 403
    assert key(r) == "error.403.write_requires_account"


@pytest.fixture
def notification_bus(monkeypatch):
    """Requests as the bus receives them, after core's own validation ran."""
    published = []
    monkeypatch.setattr(
        "stapel_core.notifications.publish.publish",
        lambda topic, event: published.append(event.payload),
    )
    return published


def _delivered(published):
    """What an intake honouring ``dedup_key`` delivers: the first per key."""
    claimed, out = set(), []
    for payload in published:
        claim = (payload["notification_type"], payload.get("dedup_key"))
        if payload.get("dedup_key") and claim in claimed:
            continue
        claimed.add(claim)
        out.append(payload)
    return out


def test_reaction_notification_is_debounced_per_target(client_for, user, other_user, staff, graph,
                                                      notification_bus,
                                                      django_capture_on_commit_callbacks):
    p = make_post(user)
    other = make_post(user)
    with django_capture_on_commit_callbacks(execute=True):
        _put(client_for(other_user), p.pk)
        _put(client_for(staff), p.pk)
        _put(client_for(user), p.pk)  # own reaction: never notified
        _put(client_for(other_user), other.pk)
    reactions = [n for n in notification_bus if n["notification_type"] == "feed.reaction_received"]
    assert [(n["user_id"], n["dedup_key"], n["dedup_ttl"]) for n in reactions] == [
        (str(user.pk), f"feed:notify:reaction:post:{p.pk}", 600),
        (str(user.pk), f"feed:notify:reaction:post:{p.pk}", 600),
        (str(user.pk), f"feed:notify:reaction:post:{other.pk}", 600),
    ]
    delivered = _delivered(reactions)
    assert [(n["variables"]["actor_id"], n["variables"]["post_id"]) for n in delivered] == [
        (str(other_user.pk), str(p.pk)),
        (str(other_user.pk), str(other.pk)),
    ]


def test_the_feed_keeps_no_debounce_state_of_its_own(client_for, user, other_user, graph,
                                                     notification_bus,
                                                     django_capture_on_commit_callbacks):
    """The window is the intake's: a cleared cache changes nothing here."""
    from django.core.cache import cache

    p = make_post(user)
    with django_capture_on_commit_callbacks(execute=True):
        _put(client_for(other_user), p.pk)
        _put(client_for(other_user), p.pk)  # off
        cache.clear()
        _put(client_for(other_user), p.pk)  # on again
    keys = [n["dedup_key"] for n in notification_bus
            if n["notification_type"] == "feed.reaction_received"]
    assert keys == [f"feed:notify:reaction:post:{p.pk}"] * 2
    assert len(_delivered(notification_bus)) == 1


def test_activity_signal_reaches_the_post_author(client_for, user, other_user, graph,
                                                 monkeypatch, django_capture_on_commit_callbacks):
    seen = []
    monkeypatch.setattr("stapel_core.comm.signal", lambda key, name, payload: seen.append((key, name, payload)))
    p = make_post(user)
    with django_capture_on_commit_callbacks(execute=True):
        _put(client_for(other_user), p.pk)
    assert seen == [(f"feed:user:{user.pk}", "feed.activity", {"post_id": str(p.pk)})]


@pytest.mark.django_db(transaction=True)
class TestInterleavedWriters:
    """Two writers on one target: unique rows, honest counts."""

    def test_same_user_racing_insert_ends_as_one_row(self, user, other_user, graph, monkeypatch):
        p = make_post(user)
        real = reaction_service._existing
        state = {"raced": False}

        def stale_read(target_type, target_key, uid):
            if not state["raced"]:
                # Our read says "none"; the rival request's row lands right after.
                state["raced"] = True
                Reaction.objects.create(target_type=target_type, target_key=target_key,
                                        user_id=uid, kind="like")
                return None
            return real(target_type, target_key, uid)

        monkeypatch.setattr(reaction_service, "_existing", stale_read)
        state_out = reaction_service.toggle(str(other_user.pk), "post", p.pk, "like", active=True)
        assert state["raced"]
        assert state_out.active is True
        assert Reaction.objects.filter(user_id=str(other_user.pk)).count() == 1
        assert Post.objects.get(pk=p.pk).reaction_counts == {"like": 1}

    def test_two_users_interleaved_lose_no_count(self, user, other_user, staff, graph, monkeypatch):
        """B's whole toggle runs between A's insert and A's count write."""
        p = make_post(user)
        from stapel_feed.services import counters

        real_recount = counters.recount_post
        state = {"nested": False}

        def interleaved(post):
            if not state["nested"]:
                state["nested"] = True
                reaction_service.toggle(str(staff.pk), "post", p.pk, "like")
            return real_recount(post)

        monkeypatch.setattr(reaction_service, "recount_post", interleaved)
        reaction_service.toggle(str(other_user.pk), "post", p.pk, "like")
        assert state["nested"]
        assert Reaction.objects.filter(target_key=str(p.pk)).count() == 2
        assert Post.objects.get(pk=p.pk).reaction_counts == {"like": 2}

    def test_writes_lock_the_target_row(self, user, other_user, graph, monkeypatch):
        """The lock is asked for (SQLite drops FOR UPDATE, so ask the ORM)."""
        from django.db.models import QuerySet

        p = make_post(user)
        seen = []
        real = QuerySet.select_for_update

        def spy(self, *args, **kwargs):
            seen.append(self.model.__name__)
            return real(self, *args, **kwargs)

        monkeypatch.setattr(QuerySet, "select_for_update", spy)
        reaction_service.toggle(str(other_user.pk), "post", p.pk, "like")
        assert "Post" in seen
