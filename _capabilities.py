"""stapel-feed capabilities.json emitter — thin shim over stapel_tools.capabilities."""
from pathlib import Path

from stapel_tools.capabilities import axis_group_rules, run_capabilities_cli


def main(argv=None):
    from stapel_feed._codegen import _configure

    _configure()
    from stapel_feed.conf import DEFAULTS
    from stapel_feed.urls import GATE_REGISTRY

    # Two CTO-facing axes, both behavioural (no endpoint is unmounted):
    # PUBLIC_READ (anonymous reads) and WRITE_REQUIRES_ACCOUNT (guest writes).
    axes = {"PUBLIC_READ", "WRITE_REQUIRES_ACCOUNT"}
    return run_capabilities_cli(
        argv,
        repo=Path(__file__).resolve().parent,
        canonical_prefix="/feed/api/v1",
        defaults=DEFAULTS,
        registry=GATE_REGISTRY,
        is_axis=lambda k: k in axes,
        axis_group=axis_group_rules(
            exact={
                "PUBLIC_READ": "feed.read",
                "WRITE_REQUIRES_ACCOUNT": "feed.write",
            }
        ),
        prog="stapel-feed-capabilities",
    )


if __name__ == "__main__":
    raise SystemExit(main())
