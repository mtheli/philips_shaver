"""Structural guards for the translation files and the dialogs using them.

Three failure modes these catch, all of which surface as broken UI rather
than as an exception:

* A step the flow renders has no entry in strings.json — the dialog comes
  up blank.
* A translation drops or renames a placeholder — Home Assistant leaves the
  raw ``{name}`` in the text, or the step fails to format.
* ``errors`` set on a form without input fields — invisible to the user.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "philips_shaver"
FLOW_SRC = (COMPONENT_DIR / "config_flow.py").read_text(encoding="utf-8")
STRINGS = json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
TRANSLATIONS = sorted((COMPONENT_DIR / "translations").glob("*.json"))

# Selected at runtime through errors[] or an error_key, never by literal
# name — so the dead-block check cannot see them.
ERROR_KEYS = {
    "abort_if_unique_id_configured",
    "cannot_connect",
    "connection_aborted",
    "device_asleep",
    "device_not_found",
    "no_esphome_devices",
    "not_paired",
    "out_of_slots",
    "pair_failed_stale_bond",
    "pair_timeout",
    "pairing_failed",
    "service_call_failed",
    "unknown",
}

# Blocks the flow selects by interpolating an outcome into the name.
DYNAMIC_BLOCKS = {
    "confirm_alert_asleep",
    "confirm_alert_aborted",
    "confirm_alert_failed",
    "confirm_warn_proxy",
    "confirm_warn_proxy_local",
    "esp_status_read_failed",
    "esp_status_read_error",
}


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def _leaf_values(obj, prefix: str = ""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _leaf_values(value, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, str):
        yield prefix, obj


def _requested_blocks() -> set[str]:
    """Block names the flow references as string literals."""
    return {
        name for name in STRINGS["config"]["error"]
        if f'"error.{name}"' in FLOW_SRC
    } | DYNAMIC_BLOCKS


def test_rendered_steps_are_defined() -> None:
    rendered = set(re.findall(r'(?<!next_)step_id\s*=\s*"(\w+)"', FLOW_SRC))
    progress_only = set(
        re.findall(r'async_show_progress\(\s*step_id="(\w+)"', FLOW_SRC)
    )
    defined = set(STRINGS["config"]["step"]) | set(
        STRINGS.get("options", {}).get("step", {})
    )
    missing = (rendered - progress_only) - defined
    assert not missing, f"steps rendered but not translated: {missing}"


def test_requested_blocks_are_defined() -> None:
    """Every injected text must exist in every language.

    A name the flow asks for but no translation defines renders as an
    empty sentence rather than raising.
    """
    for path in [COMPONENT_DIR / "strings.json", *TRANSLATIONS]:
        defined = set(
            json.loads(path.read_text(encoding="utf-8"))["config"]["error"]
        )
        missing = _requested_blocks() - defined
        assert not missing, f"{path.name}: text blocks missing: {missing}"


def test_no_dead_blocks() -> None:
    """The reverse check — a block nothing asks for is dead weight."""
    orphans = set(STRINGS["config"]["error"]) - ERROR_KEYS - _requested_blocks()
    assert not orphans, f"blocks defined but never used: {orphans}"


def test_translations_keep_every_placeholder() -> None:
    """A translated string must use exactly the placeholders of its source.

    A dropped placeholder silently hides a name or reading; an added one
    raises KeyError when the step renders.
    """
    source = dict(_leaf_values(STRINGS))
    for path in TRANSLATIONS:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in _leaf_values(data):
            if key not in source:
                continue
            assert _placeholders(value) == _placeholders(source[key]), (
                f"{path.name}: placeholder mismatch at {key}"
            )


def test_no_html_in_translation_values() -> None:
    """hassfest rejects HTML in translation values (release blocker)."""
    for path in [COMPONENT_DIR / "strings.json", *TRANSLATIONS]:
        data = json.loads(path.read_text(encoding="utf-8"))
        offenders = [
            key for key, value in _leaf_values(data)
            if re.search(r"</?[a-zA-Z][^>]*>", value)
        ]
        assert not offenders, f"{path.name}: HTML in {offenders}"


def _is_empty_schema(node) -> bool:
    """True for ``vol.Schema({})``, a bare ``{}`` and ``None``."""
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "Schema" and node.args:
            inner = node.args[0]
            return isinstance(inner, ast.Dict) and not inner.keys
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    return isinstance(node, ast.Dict) and not node.keys


def test_no_errors_on_a_form_without_fields() -> None:
    """``errors`` never reaches the user on a form that has no fields.

    The frontend renders backend errors only inside ``ha-form``, and skips
    that element when ``data_schema`` is empty or absent (a change in HA
    2026.6 — before that the form was always rendered). Setting ``errors``
    there fails silently: the flow returns the same dialog with no hint
    why, which is exactly what it looks like when nothing happened at all.

    Such a step has to carry its reason in the description instead.
    """
    offenders = []
    for node in ast.walk(ast.parse(FLOW_SRC)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "async_show_form":
            continue
        kwargs = {k.arg: k.value for k in node.keywords}
        if "errors" not in kwargs:
            continue
        schema = kwargs.get("data_schema")
        if schema is None:
            offenders.append((node.lineno, "no data_schema"))
        elif _is_empty_schema(schema):
            offenders.append((node.lineno, "empty data_schema"))
    assert not offenders, (
        "errors set on a field-less form (invisible to the user): "
        + ", ".join(f"config_flow.py:{line} ({why})" for line, why in offenders)
    )
