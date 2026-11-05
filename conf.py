"""Settings namespace for stapel-feed.

All configuration is read through ``feed_settings`` (lazily, at call time).
Resolution order per key: ``settings.STAPEL_FEED`` dict -> flat Django
setting of the same name -> environment variable -> default below.

The feed owns posts, comments and reactions. Who follows whom and who
blocked whom is profiles' data, read through ONE comm Function
(``SOCIAL_GRAPH_FUNCTION``); author cards and attachment metadata are read
by name too (``CARDS_FUNCTION``, ``MEDIA_FUNCTION``). The feed never imports
a sibling module.
"""
from stapel_core.conf import AppSettings

#: AppSettings-shaped literal dict: a top-level DEFAULTS lets the
#: capabilities.json emitter introspect axis keys/kinds.
DEFAULTS = {
    # Axis: may an unauthenticated visitor read the public surfaces
    # (public/, authors/<id>/posts/, posts/<id>/, comments)? False -> 401.
    "PUBLIC_READ": True,
    # Axis: may a stapel-auth guest row write (post, comment, react)?
    # True -> error.403.write_requires_account.
    "WRITE_REQUIRES_ACCOUNT": True,
    # Reaction kinds a client may send. REPLACES the default tuple.
    "REACTION_KINDS": ("like",),
    # Minutes after creation during which the author may edit; 0 = never.
    "EDIT_WINDOW_MINUTES": 15,
    # Followed authors home/ fans in at most; over it the graph answers
    # truncated and home serves the first N (newest follows first).
    "FOLLOWING_MAX": 5000,
    # Attachments (opaque CDN refs) per post.
    "MAX_ATTACHMENTS": 10,
    # Dotted comm Function name answering {user_id, limit} ->
    # {following, blocked, truncated}. REPLACE for a host with its own graph.
    "SOCIAL_GRAPH_FUNCTION": "profiles.social_graph",
    # Author cards, batched per page ({user_ids} -> {profiles, missing});
    # "" disables (cards render null).
    "CARDS_FUNCTION": "profiles.public_cards",
    # Attachment render metadata ({refs} -> {items, missing}); "" disables
    # (image objects keep the ref, meta_reason="cdn_unavailable").
    "MEDIA_FUNCTION": "cdn.describe_many",
    # Best-effort notifications to the post author (comments, reactions).
    "NOTIFY": True,
    # One notification per follower on every new post: reserved (see
    # MODULE.md); True is system check W003 until a followers Function exists.
    "NOTIFY_FOLLOWERS": False,
    # "{post_id}" template for notification and moderation links; "" = none.
    "POST_URL_TEMPLATE": "",
}

feed_settings = AppSettings(
    "STAPEL_FEED",
    defaults=DEFAULTS,
)

__all__ = ["feed_settings", "DEFAULTS"]
