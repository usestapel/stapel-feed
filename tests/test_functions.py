"""feed.counts and feed.export."""
import pytest
from stapel_core.comm import call

from stapel_feed.models import ContentStatus

from .factories import make_post

pytestmark = pytest.mark.django_db


def test_counts_published_only(user):
    make_post(user)
    make_post(user, status=ContentStatus.BLOCKED)
    assert call("feed.counts", {"user_id": str(user.pk)}) == {"posts": 1}


def test_export_pages_with_a_cursor_and_no_body(user):
    posts = [make_post(user, body="secret") for _ in range(3)]
    first = call("feed.export", {"limit": 2})
    assert [r["post_id"] for r in first["rows"]] == [str(p.pk) for p in posts[:2]]
    assert first["total"] == 3 and first["cursor"] == str(posts[1].pk)
    assert all("body" not in r for r in first["rows"])
    second = call("feed.export", {"limit": 2, "cursor": first["cursor"]})
    assert [r["post_id"] for r in second["rows"]] == [str(posts[2].pk)]
    assert second["cursor"] is None
