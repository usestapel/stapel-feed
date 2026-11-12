"""Fake neighbours: the graph and the card Functions profiles would answer."""
from __future__ import annotations


class _FakeFunction:
    name = ""

    def __init__(self):
        self.calls: list[dict] = []
        self.fail = False

    def install(self):
        from stapel_core.comm.registry import function_registry

        function_registry.register(self.name, self)

    def uninstall(self):
        from stapel_core.comm.registry import function_registry

        with function_registry._lock:
            function_registry._providers.pop(self.name, None)
            function_registry._schemas.pop(self.name, None)


class FakeGraph(_FakeFunction):
    """``profiles.social_graph`` over in-memory follow/block edges."""

    name = "profiles.social_graph"

    def __init__(self):
        super().__init__()
        self.follows: set[tuple[str, str]] = set()
        self.blocks: set[tuple[str, str]] = set()

    def follow(self, a, b):
        self.follows.add((str(a), str(b)))

    def block(self, blocker, blocked):
        self.blocks.add((str(blocker), str(blocked)))

    def __call__(self, payload):
        self.calls.append(dict(payload))
        if self.fail:
            raise RuntimeError("profiles is down")
        me = str(payload["user_id"])
        blocked = sorted({b for a, b in self.blocks if a == me} | {a for a, b in self.blocks if b == me})
        following = sorted(b for a, b in self.follows if a == me and b not in blocked)
        limit = payload.get("limit")
        truncated = limit is not None and len(following) > int(limit)
        if truncated:
            following = following[: int(limit)]
        return {"following": following, "blocked": blocked, "truncated": truncated}


class FakeCards(_FakeFunction):
    """``profiles.public_cards``: a card for every id it knows."""

    name = "profiles.public_cards"

    def __init__(self):
        super().__init__()
        self.names: dict[str, str] = {}
        self.avatars: dict[str, dict] = {}

    def __call__(self, payload):
        self.calls.append(dict(payload))
        if self.fail:
            raise RuntimeError("profiles is down")
        ids = [str(u) for u in payload["user_ids"]]
        return {
            "profiles": {
                u: {"user_id": u, "display_name": self.names[u], "avatar": self.avatars.get(u),
                    "member_since": None, "seller_type": None}
                for u in ids if u in self.names
            },
            "missing": [u for u in ids if u not in self.names],
        }
