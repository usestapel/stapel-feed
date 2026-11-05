"""System checks: each fires on its defect and is silent on the default."""
from django.test import override_settings

from stapel_feed import checks


def _ids(findings):
    return [f.id for f in findings]


def test_reaction_kinds_default_is_fine():
    assert checks.check_reaction_kinds(None) == []


@override_settings(STAPEL_FEED={"REACTION_KINDS": ()})
def test_empty_reaction_kinds_e001():
    assert _ids(checks.check_reaction_kinds(None)) == ["stapel_feed.E001"]


@override_settings(STAPEL_FEED={"REACTION_KINDS": ("Like!",)})
def test_bad_reaction_kind_e001():
    assert _ids(checks.check_reaction_kinds(None)) == ["stapel_feed.E001"]


def test_unreachable_graph_w001():
    assert _ids(checks.check_social_graph(None)) == ["stapel_feed.W001"]


def test_reachable_graph_is_silent(graph):
    assert checks.check_social_graph(None) == []


def test_bounds_default_is_fine():
    assert checks.check_bounds(None) == []


@override_settings(STAPEL_FEED={"MAX_ATTACHMENTS": 101, "EDIT_WINDOW_MINUTES": -1})
def test_bounds_e002():
    assert _ids(checks.check_bounds(None)) == ["stapel_feed.E002", "stapel_feed.E002"]


def test_notify_followers_default_is_silent():
    assert checks.check_notify_followers(None) == []


@override_settings(STAPEL_FEED={"NOTIFY_FOLLOWERS": True})
def test_notify_followers_w003():
    assert _ids(checks.check_notify_followers(None)) == ["stapel_feed.W003"]
