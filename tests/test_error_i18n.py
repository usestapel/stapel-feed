"""Localized error catalogs (``translations/errors.<lang>.json``) + reference.

The convention of stapel-profiles: the en canon is the registry
(``errors.py`` → ``docs/errors.json``); every target language ships a flat
``translations/errors.<lang>.json`` with the shared ``translations/.state.json``
provenance sidecar, and ``docs/errors.<lang>.md`` is the per-language error
reference. :func:`check_translation_catalogs` gates coverage, staleness,
placeholders and byte stability. Core-owned keys are core's to translate and
never copied here.

The strings are machine translations kept in :data:`_MACHINE` (``origin:
llm``), so the catalog regenerates deterministically without a live model.
Adding a language: append it to :data:`LANGUAGES`, add its table, regenerate.

Regenerate after adding/changing an error key or a translation:

    STAPEL_REGEN_ERROR_I18N=1 python -m pytest tests/test_error_i18n.py::test_regen

then commit ``translations/`` + ``docs/errors.<lang>.md``. Without the env
var the same module is the CI gate.
"""
import io
import os
import tomllib
from pathlib import Path

import pytest
from django.core.management import call_command
from stapel_core.i18n import (
    check_translation_catalogs,
    source_texts,
    summarize,
    translate_catalog,
)
from stapel_core.i18n.catalogs import load_catalog_file

REPO = Path(__file__).resolve().parent.parent
TRANSLATIONS = REPO / "translations"
DOCS = REPO / "docs"
THIS_PACKAGE = "stapel_feed"
LANGUAGES = ["en", "ru", "es"]
TARGET_LANGUAGES = [lang for lang in LANGUAGES if lang != "en"]

_MACHINE_RU = {
    "error.400.attachment_ref_invalid": "Это вложение не является корректной ссылкой на загрузку",
    "error.400.too_many_attachments": "К посту можно прикрепить не более {max} вложений",
    "error.400.reaction_kind_unknown": "Неизвестная реакция",
    "error.403.write_requires_account": "Войдите, чтобы публиковать, комментировать или реагировать",
    "error.403.home_requires_account": "Войдите, чтобы видеть тех, на кого вы подписаны",
    "error.403.blocked": "Вы не можете взаимодействовать с этим человеком",
    "error.403.not_author": "Это может сделать только автор",
    "error.404.post_not_found": "Пост не найден",
    "error.404.comment_not_found": "Комментарий не найден",
    "error.409.edit_window_closed": "Этот пост больше нельзя редактировать",
    "error.503.social_graph_unavailable": "Лента временно недоступна, попробуйте чуть позже",
}

_MACHINE_ES = {
    "error.400.attachment_ref_invalid": "Este adjunto no es una referencia de subida válida",
    "error.400.too_many_attachments": "Una publicación admite como máximo {max} adjuntos",
    "error.400.reaction_kind_unknown": "Reacción desconocida",
    "error.403.write_requires_account": "Inicia sesión para publicar, comentar o reaccionar",
    "error.403.home_requires_account": "Inicia sesión para ver a las personas que sigues",
    "error.403.blocked": "No puedes interactuar con esta persona",
    "error.403.not_author": "Solo el autor puede hacer esto",
    "error.404.post_not_found": "Publicación no encontrada",
    "error.404.comment_not_found": "Comentario no encontrado",
    "error.409.edit_window_closed": "Esta publicación ya no se puede editar",
    "error.503.social_graph_unavailable": "El feed no está disponible por el momento; inténtalo de nuevo en breve",
}

_MACHINE = {"ru": _MACHINE_RU, "es": _MACHINE_ES}


class _DictTranslator:
    """Offline translator seam — returns fixed machine translations by key."""

    def __init__(self, table):
        self._table = table

    def translate(self, entries, source_language, target_language):
        return {k: self._table[k] for k in entries if k in self._table}


def _regen(lang: str):
    return translate_catalog(
        "errors", lang, TRANSLATIONS,
        source_texts=source_texts("errors"),
        llm=True,
        translator=_DictTranslator(_MACHINE[lang]),
    )


def _owned() -> dict[str, str]:
    from stapel_core.i18n import owned_keys, source_owners

    return owned_keys(source_texts("errors"), source_owners("errors"), THIS_PACKAGE)


def test_regen():
    """Regenerate (env-gated) or assert every catalog is a no-op regen (drift)."""
    if os.environ.get("STAPEL_REGEN_ERROR_I18N"):
        for lang in TARGET_LANGUAGES:
            result = _regen(lang)
            assert not result.missing, f"{lang}: still missing: {result.missing}"
        for lang in LANGUAGES:
            call_command("generate_error_docs", "--lang", lang,
                         "--out", str(DOCS), "--translations", str(TRANSLATIONS),
                         stdout=io.StringIO())
        return

    for lang in TARGET_LANGUAGES:
        path = TRANSLATIONS / f"errors.{lang}.json"
        before = path.read_bytes()
        _regen(lang)
        assert path.read_bytes() == before, (
            f"errors.{lang}.json drifted — run "
            f"STAPEL_REGEN_ERROR_I18N=1 pytest tests/test_error_i18n.py::test_regen"
        )


def test_catalog_gate_green():
    """Missing / stale / params / byte-stability / foreign: all zero."""
    issues = check_translation_catalogs(
        "errors", TRANSLATIONS,
        source_texts=source_texts("errors"),
        languages=LANGUAGES,
        owner=THIS_PACKAGE,
    )
    errors, _warnings = summarize(issues)
    blocking = [i for i in issues if i.level == "error"]
    assert not blocking, "\n".join(f"[{i.code}/{i.language}] {i.message}" for i in blocking)
    assert errors == 0


def test_every_language_covers_every_code_in_errors_py():
    from stapel_feed.errors import STAPEL_FEED_ERRORS

    owned = _owned()
    assert set(owned) == set(STAPEL_FEED_ERRORS), (
        "the loader does not attribute this module's registry to it"
    )
    for lang in TARGET_LANGUAGES:
        catalog = load_catalog_file(TRANSLATIONS / f"errors.{lang}.json")
        missing = sorted(set(STAPEL_FEED_ERRORS) - set(catalog))
        assert not missing, f"{lang} catalog misses {missing}"
        empty = sorted(k for k, v in catalog.items() if not str(v).strip())
        assert not empty, f"{lang}: empty translation(s): {empty}"


@pytest.mark.parametrize("lang", TARGET_LANGUAGES)
def test_the_catalog_carries_nothing_but_owned_keys(lang):
    stray = sorted(set(load_catalog_file(TRANSLATIONS / f"errors.{lang}.json")) - set(_owned()))
    assert not stray, f"{lang}: not this module's keys: {stray}"


@pytest.mark.parametrize("lang", TARGET_LANGUAGES)
def test_translations_preserve_placeholders(lang):
    from stapel_core.i18n.domains import params_of

    canon = _owned()
    for key, text in load_catalog_file(TRANSLATIONS / f"errors.{lang}.json").items():
        assert set(params_of(text)) == set(params_of(canon[key])), f"{lang}: {key}"


def test_the_shipped_language_set_is_exactly_the_gated_one():
    shipped = {p.name for p in TRANSLATIONS.glob("errors.*.json")}
    assert shipped == {f"errors.{lang}.json" for lang in TARGET_LANGUAGES}


def test_error_reference_matches_a_fresh_regeneration(tmp_path):
    for lang in LANGUAGES:
        call_command("generate_error_docs", "--lang", lang, "--out", str(tmp_path),
                     "--translations", str(TRANSLATIONS), stdout=io.StringIO())
        assert (tmp_path / f"errors.{lang}.md").read_bytes() == \
            (DOCS / f"errors.{lang}.md").read_bytes(), (
                f"docs/errors.{lang}.md is stale — run "
                f"STAPEL_REGEN_ERROR_I18N=1 pytest tests/test_error_i18n.py::test_regen"
            )


def test_error_reference_has_no_en_fallback_rows():
    for lang in TARGET_LANGUAGES:
        assert "_(en)_" not in (DOCS / f"errors.{lang}.md").read_text(), (
            f"{lang} error reference has en-fallback rows — the catalog is incomplete"
        )


def test_the_wheel_ships_the_catalogue():
    """package-data must carry ``translations/*.json``, or no host reads it."""
    with open(REPO / "pyproject.toml", "rb") as handle:
        patterns = tomllib.load(handle)["tool"]["setuptools"]["package-data"]
    assert "translations/*.json" in patterns[THIS_PACKAGE]
