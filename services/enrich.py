"""Author cards and attachment metadata, asked by name, batched per page.

Both degrade instead of failing: a page of posts still renders when
profiles or the CDN is down — the card is ``null``, the image object keeps
its ref with ``meta_reason="cdn_unavailable"``.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

META_OK = "ok"
META_PARTIAL = "partial"
META_MISSING = "missing"
REASON_CDN_UNAVAILABLE = "cdn_unavailable"
REASON_UNKNOWN_REF = "unknown_ref"

#: Every key an image object carries besides ``ref`` — the shape stapel-cdn's
#: ``describe_many`` answers and profiles' card avatar carries.
IMAGE_KEYS = (
    "mime", "ext", "bytes", "width", "height", "aspect", "square",
    "animated", "preview_b64", "preview_kind", "variants",
)


def _call(name: str, payload: dict):
    from stapel_core.comm import call, function_unreachable_reason

    if not name:
        return None
    if function_unreachable_reason(name):
        return None
    try:
        return call(name, payload)
    except Exception:  # noqa: BLE001 — degradation is data
        logger.info("feed: %r unavailable", name, exc_info=True)
        return None


def author_cards(user_ids) -> dict:
    """``{user_id: {user_id, display_name, avatar}}`` for the ids that have a card."""
    from ..conf import feed_settings

    ids = sorted({str(u) for u in user_ids if u})
    if not ids:
        return {}
    reply = _call(str(feed_settings.CARDS_FUNCTION or ""), {"user_ids": ids})
    if not isinstance(reply, dict) or not isinstance(reply.get("profiles"), dict):
        return {}
    cards = {}
    for user_id, card in reply["profiles"].items():
        if not isinstance(card, dict):
            continue
        avatar = card.get("avatar")
        cards[str(user_id)] = {
            "user_id": str(user_id),
            "display_name": str(card.get("display_name") or ""),
            "avatar": avatar if isinstance(avatar, dict) and avatar.get("ref") else None,
        }
    return cards


def _image(ref: str, snapshot: dict | None, reason: str | None) -> dict:
    image = {"ref": ref, **{key: None for key in IMAGE_KEYS}}
    image["variants"] = []
    if not snapshot:
        image["meta_status"] = META_MISSING if reason == REASON_UNKNOWN_REF else META_PARTIAL
        image["meta_reason"] = reason
        return image
    for key in IMAGE_KEYS:
        if key in snapshot:
            image[key] = snapshot[key]
    image["variants"] = list(snapshot.get("variants") or [])
    image["meta_status"] = str(snapshot.get("meta_status") or META_OK)
    image["meta_reason"] = snapshot.get("meta_reason")
    return image


def image_objects(refs) -> dict:
    """``{ref: image object}`` for every ref, one ``describe_many`` call."""
    from ..conf import feed_settings

    unique = list(dict.fromkeys(str(r) for r in refs if r))
    if not unique:
        return {}
    reply = _call(str(feed_settings.MEDIA_FUNCTION or ""), {"refs": unique})
    if not isinstance(reply, dict):
        return {ref: _image(ref, None, REASON_CDN_UNAVAILABLE) for ref in unique}
    items = reply.get("items") or {}
    missing = set(reply.get("missing") or [])
    out = {}
    for ref in unique:
        snapshot = items.get(ref) if isinstance(items, dict) else None
        reason = REASON_UNKNOWN_REF if ref in missing else (None if snapshot else REASON_CDN_UNAVAILABLE)
        out[ref] = _image(ref, snapshot if isinstance(snapshot, dict) else None, reason)
    return out


__all__ = ["IMAGE_KEYS", "author_cards", "image_objects"]
