"""Root URLconf for stapel-feed — v1 canon mount.

The host mounts the module under ``feed/api/``; this module contributes
the ``v1/`` segment:

    path("feed/api/", include("stapel_feed.urls"))   # -> /feed/api/v1/...
"""
from django.urls import include, path

from stapel_feed.urls_v1 import GATE_REGISTRY  # noqa: F401  (re-export)

urlpatterns = [
    path("v1/", include("stapel_feed.urls_v1")),
]
