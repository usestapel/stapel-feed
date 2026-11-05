"""The social graph client: whom a viewer follows and whom the feed hides.

Following and blocks are profiles' data, read through ONE comm Function
(``SOCIAL_GRAPH_FUNCTION``, default ``profiles.social_graph``)::

    {"user_id": str, "limit": int} -> {"following": [ids], "blocked": [ids],
                                        "truncated": bool}

``blocked`` is undirected (a block placed by either side). The rule this
module lives by: a feed that shows a blocked author because the block check
was down is the erasure failing where a stranger notices. So
:class:`GraphUnavailable` is never turned into "follows nobody, blocks
nobody" on ``home``/``public`` — those answer 503. Reads that can fail
closed without the graph (one author's page, one post) degrade instead:
only public posts, no follower-only content.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class GraphUnavailable(Exception):
    """The graph Function cannot be reached or answered something unusable."""


@dataclass(frozen=True)
class Graph:
    """One viewer's graph, parsed. ``known=False`` means "could not ask"."""

    following: frozenset = field(default_factory=frozenset)
    blocked: frozenset = field(default_factory=frozenset)
    truncated: bool = False
    known: bool = True

    def follows(self, user_id: str) -> bool:
        return str(user_id) in self.following

    def blocks(self, user_id: str) -> bool:
        return str(user_id) in self.blocked


#: The graph of a viewer nobody could ask about (anonymous, or degraded).
NOBODY = Graph()
UNKNOWN = Graph(known=False)


def _ids(name: str, value) -> frozenset:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise GraphUnavailable(f"graph Function answered a non-list {name!r}")
    return frozenset(value)


def fetch_graph(user_id: str) -> Graph:
    """Ask the graph Function about ``user_id``. Raises :class:`GraphUnavailable`."""
    from stapel_core.comm import CommError, call, function_unreachable_reason

    from ..conf import feed_settings

    name = str(feed_settings.SOCIAL_GRAPH_FUNCTION or "")
    if not name:
        raise GraphUnavailable("SOCIAL_GRAPH_FUNCTION is empty")
    reason = function_unreachable_reason(name)
    if reason:
        raise GraphUnavailable(f"{name}: {reason}")
    try:
        reply = call(name, {"user_id": str(user_id), "limit": int(feed_settings.FOLLOWING_MAX)})
    except CommError as exc:
        raise GraphUnavailable(f"{name} failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — in-process provider raised
        raise GraphUnavailable(f"{name} raised: {exc!r}") from exc
    if not isinstance(reply, dict):
        raise GraphUnavailable(f"{name} answered {type(reply).__name__}, not an object")
    graph = Graph(
        following=_ids("following", reply.get("following")),
        blocked=_ids("blocked", reply.get("blocked")),
        truncated=bool(reply.get("truncated")),
    )
    if graph.truncated:
        logger.info("feed: graph of %s truncated at FOLLOWING_MAX", user_id)
    return graph


def graph_or_unknown(user_id: str | None) -> Graph:
    """For reads that degrade: the graph, :data:`NOBODY` for anonymous,
    :data:`UNKNOWN` when the Function is down."""
    if not user_id:
        return NOBODY
    try:
        return fetch_graph(user_id)
    except GraphUnavailable:
        logger.warning("feed: social graph unavailable for %s; degrading", user_id, exc_info=True)
        return UNKNOWN


__all__ = ["Graph", "GraphUnavailable", "NOBODY", "UNKNOWN", "fetch_graph", "graph_or_unknown"]
