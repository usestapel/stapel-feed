"""Every response body the committed schema declares is the body the views send.

The operation list is DERIVED from ``docs/schema.json``: an operation with a
declared JSON 2xx body and no recipe here fails loudly. Every body is
validated against its declared schema (OAS ``nullable`` honoured), in a
populated and an empty state where the read has one.
"""
import copy
import json
from pathlib import Path

import jsonschema
import pytest

from .factories import make_comment, make_post

REPO = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((REPO / "docs" / "schema.json").read_text())
V1 = "/feed/api/v1"

pytestmark = pytest.mark.django_db


def _json_schema(node):
    if isinstance(node, list):
        return [_json_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    rebuilt = {k: _json_schema(v) for k, v in node.items() if k != "nullable"}
    if node.get("nullable"):
        return {"anyOf": [rebuilt, {"type": "null"}]}
    return rebuilt


def _validator(body_schema):
    root = copy.deepcopy(body_schema)
    root["components"] = copy.deepcopy(SCHEMA["components"])
    return jsonschema.Draft202012Validator(_json_schema(root))


def _operations():
    ops = []
    for path, methods in SCHEMA["paths"].items():
        for method, op in methods.items():
            for code, response in op.get("responses", {}).items():
                body = response.get("content", {}).get("application/json", {}).get("schema")
                if body is not None and code.startswith("2"):
                    ops.append((method.upper(), path, int(code), body))
    return sorted(ops, key=lambda o: (o[1], o[0], o[2]))


OPERATIONS = _operations()


class Env:
    def __init__(self, client_for, user, other_user, graph, cards):
        self.client_for, self.user, self.other = client_for, user, other_user
        self.graph, self.cards = graph, cards
        self.client = client_for(user)
        cards.names[str(user.pk)] = "Alice"


def _populated_post(env):
    post = make_post(env.user, attachments=["image/abc"])
    make_comment(post, env.other)
    env.graph.follow(env.user.pk, env.other.pk)
    make_post(env.other)
    return post


def r_home(env):
    client = env.client
    empty = client.get(f"{V1}/home/")
    _populated_post(env)
    return [client.get(f"{V1}/home/"), empty]


def r_public(env):
    client = env.client
    empty = client.get(f"{V1}/public/")
    _populated_post(env)
    return [client.get(f"{V1}/public/"), empty]


def r_author(env):
    client = env.client
    empty = client.get(f"{V1}/authors/{env.other.pk}/posts/")
    _populated_post(env)
    return [client.get(f"{V1}/authors/{env.user.pk}/posts/"), empty]


def r_create(env):
    client = env.client
    return [client.post(f"{V1}/posts/", {"body": "x", "attachments": ["image/a"]}, format="json")]


def r_detail(env):
    client = env.client
    post = _populated_post(env)
    return [client.get(f"{V1}/posts/{post.pk}/")]


def r_patch(env):
    client = env.client
    post = _populated_post(env)
    return [client.patch(f"{V1}/posts/{post.pk}/", {"body": "y"}, format="json")]


def r_comments(env):
    client = env.client
    post = _populated_post(env)
    bare = make_post(env.user)
    return [client.get(f"{V1}/posts/{post.pk}/comments/"),
            client.get(f"{V1}/posts/{bare.pk}/comments/")]


def r_comment_create(env):
    client = env.client
    post = _populated_post(env)
    return [client.post(f"{V1}/posts/{post.pk}/comments/", {"body": "c"}, format="json")]


def r_reaction(env):
    post = _populated_post(env)
    other_client = env.client_for(env.other)
    url = f"{V1}/reactions/"
    body = {"target_type": "post", "target_key": str(post.pk)}
    return [other_client.put(url, body, format="json"), other_client.put(url, body, format="json")]


RECIPES = {
    ("GET", "/feed/api/v1/home/", 200): r_home,
    ("GET", "/feed/api/v1/public/", 200): r_public,
    ("GET", "/feed/api/v1/authors/{user_id}/posts/", 200): r_author,
    ("POST", "/feed/api/v1/posts/", 201): r_create,
    ("GET", "/feed/api/v1/posts/{post_id}/", 200): r_detail,
    ("PATCH", "/feed/api/v1/posts/{post_id}/", 200): r_patch,
    ("GET", "/feed/api/v1/posts/{post_id}/comments/", 200): r_comments,
    ("POST", "/feed/api/v1/posts/{post_id}/comments/", 201): r_comment_create,
    ("PUT", "/feed/api/v1/reactions/", 200): r_reaction,
}


def test_every_declared_body_has_a_recipe():
    declared = {(m, p, c) for m, p, c, _ in OPERATIONS}
    assert declared == set(RECIPES), declared ^ set(RECIPES)


@pytest.mark.parametrize("method,path,code,body", OPERATIONS, ids=[f"{m} {p} {c}" for m, p, c, _ in OPERATIONS])
def test_body_matches_schema(method, path, code, body, client_for, user, other_user, graph, cards):
    env = Env(client_for, user, other_user, graph, cards)
    responses = RECIPES[(method, path, code)](env)
    validator = _validator(body)
    for response in responses:
        assert response.status_code == code, response.content
        errors = sorted(validator.iter_errors(response.json()), key=str)
        assert not errors, [e.message for e in errors]
