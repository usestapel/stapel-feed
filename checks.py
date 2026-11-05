"""Django system checks for stapel-feed.

- E001  ``REACTION_KINDS`` is empty or holds a kind that is not a short slug.
- W001  the social graph Function is not reachable here: ``home`` and
        ``public`` (for members) will answer 503.
- E002  ``EDIT_WINDOW_MINUTES``, ``FOLLOWING_MAX`` or ``MAX_ATTACHMENTS`` is negative
        (or ``MAX_ATTACHMENTS`` above the wire bound of 100).
- W003  ``NOTIFY_FOLLOWERS`` is on, but no followers Function exists yet:
        nothing is sent.
"""
import re

from django.core import checks

_KIND = re.compile(r"^[a-z][a-z0-9_]{0,15}$")


@checks.register(checks.Tags.compatibility)
def check_reaction_kinds(app_configs, **kwargs):
    from .conf import feed_settings

    kinds = feed_settings.REACTION_KINDS
    if not isinstance(kinds, (list, tuple)) or not kinds or not all(
        isinstance(k, str) and _KIND.match(k) for k in kinds
    ):
        return [checks.Error(
            "STAPEL_FEED['REACTION_KINDS'] must be a non-empty tuple of short "
            "slugs (a-z, 0-9, _; at most 16 characters).",
            id="stapel_feed.E001",
        )]
    return []


@checks.register(checks.Tags.compatibility)
def check_social_graph(app_configs, **kwargs):
    from stapel_core.comm import function_unreachable_reason

    from .conf import feed_settings

    name = str(feed_settings.SOCIAL_GRAPH_FUNCTION or "")
    reason = function_unreachable_reason(name) if name else "SOCIAL_GRAPH_FUNCTION is empty"
    if reason:
        return [checks.Warning(
            f"The social graph Function {name!r} is not reachable here ({reason}). "
            "home/ and members' public/ will answer error.503.social_graph_unavailable.",
            hint="Install stapel-profiles (profiles.social_graph, >=0.23) or point "
                 "SOCIAL_GRAPH_FUNCTION at the host's own graph.",
            id="stapel_feed.W001",
        )]
    return []


@checks.register(checks.Tags.compatibility)
def check_bounds(app_configs, **kwargs):
    from .conf import feed_settings

    findings = []
    for key in ("EDIT_WINDOW_MINUTES", "FOLLOWING_MAX", "MAX_ATTACHMENTS"):
        try:
            value = int(getattr(feed_settings, key))
        except (TypeError, ValueError):
            value = -1
        if value < 0 or (key == "MAX_ATTACHMENTS" and value > 100):
            findings.append(checks.Error(
                f"STAPEL_FEED[{key!r}] must be a non-negative integer"
                + (" no larger than 100." if key == "MAX_ATTACHMENTS" else "."),
                id="stapel_feed.E002",
            ))
    return findings


@checks.register(checks.Tags.compatibility)
def check_notify_followers(app_configs, **kwargs):
    from .conf import feed_settings

    if feed_settings.NOTIFY_FOLLOWERS:
        return [checks.Warning(
            "STAPEL_FEED['NOTIFY_FOLLOWERS'] is on, but the follower fan-out is "
            "reserved: no followers Function exists yet, so nothing is sent.",
            id="stapel_feed.W003",
        )]
    return []
