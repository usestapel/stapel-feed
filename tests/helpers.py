"""Shared helpers: URLs and the error envelope's key."""
V1 = "/feed/api/v1"


def key(response) -> str:
    return response.json().get("localizable_error", "")


def ids(response) -> list[int]:
    return [item["id"] for item in response.json()["items"]]
