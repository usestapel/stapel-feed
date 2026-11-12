"""Attachment image objects: filled from the CDN, degraded without it."""
import json
from pathlib import Path

import pytest

from stapel_feed.services.enrich import author_cards, image_objects

from .factories import make_post
from .helpers import V1


#: A stapel-cdn ``describe_many`` ladder as the CDN answers it: int tiers,
#: CDN-only keys, and one rung with nothing to draw.
LADDER = [
    {"tier": 16, "branch": None, "url": "https://cdn.test/a/16.webp", "width": 16, "height": 8},
    {"tier": 480, "branch": "w", "url": "https://cdn.test/a/480w.webp", "width": 480,
     "height": 240, "watermarked": True, "clean_url": "https://cdn.test/a/clean.webp"},
    {"tier": 960, "branch": "w", "url": "https://cdn.test/a/960w.webp", "width": 960, "height": 480},
    {"tier": 1080, "branch": "w", "width": 1080, "height": 540},
]


@pytest.fixture
def cdn():
    from stapel_core.comm.registry import function_registry

    calls = []

    def describe_many(payload):
        calls.append(payload)
        return {"items": {"image/ok": {"mime": "image/jpeg", "width": 4, "height": 2,
                                       "aspect": 2.0, "variants": LADDER}},
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


def test_variants_are_typed_rungs_and_url_is_the_largest(cdn):
    image = image_objects(["image/ok"])["image/ok"]
    assert image["variants"] == [
        {"tier": "16", "branch": None, "url": "https://cdn.test/a/16.webp", "width": 16, "height": 8},
        {"tier": "480", "branch": "w", "url": "https://cdn.test/a/480w.webp", "width": 480, "height": 240},
        {"tier": "960", "branch": "w", "url": "https://cdn.test/a/960w.webp", "width": 960, "height": 480},
    ]
    assert image["url"] == "https://cdn.test/a/960w.webp"


def test_the_original_rung_is_the_default_url():
    from stapel_feed.services.enrich import _image

    image = _image("image/o", {"variants": [
        {"tier": "original", "branch": None, "url": "https://cdn.test/o.jpg", "width": 10, "height": 10},
        {"tier": 960, "branch": "w", "url": "https://cdn.test/960w.webp", "width": 960, "height": 960},
    ]}, None)
    assert image["url"] == "https://cdn.test/o.jpg"


def test_an_undescribed_image_has_no_url(cdn):
    out = image_objects(["image/gone"])
    assert out["image/gone"]["url"] is None and out["image/gone"]["variants"] == []


def test_an_avatar_from_profiles_carries_the_same_shape(cards):
    cards.names["u1"] = "Ann"
    cards.avatars["u1"] = {"ref": "image/av", "mime": "image/webp", "variants": LADDER[:1]}
    avatar = author_cards(["u1"])["u1"]["avatar"]
    assert avatar["url"] == "https://cdn.test/a/16.webp"
    assert avatar["variants"][0]["tier"] == "16"
    assert avatar["meta_status"] == "ok"


def test_the_image_object_component_types_its_rungs():
    schema = json.loads(
        (Path(__file__).resolve().parent.parent / "docs" / "schema.json").read_text()
    )["components"]["schemas"]
    image = schema["ImageObject"]["properties"]
    assert image["variants"]["items"] == {"$ref": "#/components/schemas/VariantMeta"}
    assert image["url"] == {"type": "string", "nullable": True, "maxLength": 2048}
    assert "url" in schema["ImageObject"]["required"]
    assert set(schema["VariantMeta"]["properties"]) == {"tier", "branch", "url", "width", "height"}


@pytest.mark.django_db
def test_the_wire_carries_typed_rungs_and_url(api_client, user, graph, cdn):
    make_post(user, attachments=["image/ok"])
    image = api_client.get(f"{V1}/public/").json()["items"][0]["attachments"][0]
    assert image["url"] == "https://cdn.test/a/960w.webp"
    assert image["variants"][1] == {"tier": "480", "branch": "w",
                                    "url": "https://cdn.test/a/480w.webp",
                                    "width": 480, "height": 240}
