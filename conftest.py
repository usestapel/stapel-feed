def pytest_configure(config):
    from django.conf import settings

    if not settings.configured:
        from stapel_feed._codegen_settings import settings_kwargs

        settings.configure(**settings_kwargs())
        import django

        django.setup()

        from stapel_core.comm.schemas import autoload_schemas

        autoload_schemas()


import pytest  # noqa: E402
from stapel_core.testing import emit_outside_atomic_gate  # noqa: E402,F401


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


def _make_user(username, **extra):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="x", **extra
    )


@pytest.fixture
def user(db):
    return _make_user("alice")


@pytest.fixture
def other_user(db):
    return _make_user("bob")


@pytest.fixture
def guest(db):
    return _make_user("guest-1", is_anonymous=True)


@pytest.fixture
def staff(db):
    return _make_user("staff", is_staff=True)


@pytest.fixture
def client_for(api_client):
    def _client(u):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(user=u)
        return c

    return _client


@pytest.fixture
def auth_client(client_for, user):
    return client_for(user)


@pytest.fixture
def graph():
    """The fake profiles behind ``profiles.social_graph``."""
    from stapel_feed.tests.fakes import FakeGraph

    fake = FakeGraph()
    fake.install()
    try:
        yield fake
    finally:
        fake.uninstall()


@pytest.fixture
def cards():
    """The fake profiles behind ``profiles.public_cards``."""
    from stapel_feed.tests.fakes import FakeCards

    fake = FakeCards()
    fake.install()
    try:
        yield fake
    finally:
        fake.uninstall()


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def captured_events():
    """Collect feed emits delivered in-process."""
    from stapel_core.comm import action_registry, subscribe_action

    collected = []

    def _handler(event):
        collected.append(event)

    names = ["feed.post.created", "feed.post.deleted", "feed.comment.created",
             "feed.reaction.changed"]
    for name in names:
        subscribe_action(name, _handler)
    try:
        yield collected
    finally:
        for name in names:
            handlers = action_registry._subscribers.get(name, [])
            if _handler in handlers:
                handlers.remove(_handler)
