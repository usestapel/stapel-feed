"""Attachment image objects: filled from the CDN, degraded without it."""
import pytest

from stapel_feed.services.enrich import image_objects

from .factories import make_post
from .helpers import V1


@pytest.fixture
def cdn():
    from stapel_core.comm.registry import function_registry

    calls = []

    def describe_many(payload):
        calls.append(payload)
        return {"items": {"image/ok": {"mime": "image/jpeg", "width": 4, "height": 2,
                                       "aspect": 2.0, "variants": [{"w": 2}]}},
                "missing": ["image/gone"]}

    function_registry.register("cdn.describe_many", describe_many)
    yield calls
    with function_registry._lock:
        function_registry._providers.pop("cdn.describe_many", None)


def test_known_missing_and_unanswered_refs(cdn):
    out = image_objects(["image/ok", "image/gone", "image/ok"])
    assert len(cdn) == 1 and cdn[0] == {"refs": ["image/ok", "image/gone"]}
    assert out["image/ok"]["width"] == 4 and out["image/ok"]["meta_status"] == "ok"
    assert out["image/gone"]["meta_status"] == "missing"
    assert out["image/gone"]["meta_reason"] == "unknown_ref"


def test_no_cdn_degrades_to_the_ref():
    out = image_objects(["image/x"])
    assert out["image/x"]["ref"] == "image/x"
    assert out["image/x"]["meta_reason"] == "cdn_unavailable"


@pytest.mark.django_db
def test_one_media_call_per_page(api_client, user, graph, cdn):
    make_post(user, attachments=["image/ok"])
    make_post(user, attachments=["image/ok", "image/gone"])
    body = api_client.get(f"{V1}/public/").json()
    assert len(cdn) == 1
    assert body["items"][0]["attachments"][1]["meta_status"] == "missing"
