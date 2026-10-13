"""The administration guide (`spec/10_ADMINISTRATION_GUIDE.md`) describes what is built, all of it.

What a drift would do, and the case that catches it:
- an `osprey.yaml` setting added, renamed or removed without the guide's appendix following —
  `test_the_settings_appendix_is_the_schemas_own`;
- a command or a flag nobody is told of — `test_every_command_and_install_flag_is_in_the_guide`;
- an answers-file setting nobody is told of — `test_every_answers_file_setting_is_in_the_guide`.
"""

from __future__ import annotations

import argparse

import pytest
from ospreyflow.answers import _SECTIONS, _TOP
from ospreyflow.main import _parser
from tools import admin_guide_options

GUIDE = admin_guide_options.GUIDE.read_text(encoding="utf-8")


def test_the_settings_appendix_is_the_schemas_own() -> None:
    assert admin_guide_options.guide_copy(GUIDE) == admin_guide_options.reference(), (
        "the guide's appendix A differs from the schema: run "
        "`python -m tools.admin_guide_options --write` and read what changed"
    )


def test_every_section_of_the_schema_has_its_line() -> None:
    """A new section of `osprey.yaml` needs its one line in `SECTIONS`; without it the generator
    fails with a KeyError naming it, which this makes a named failure."""
    admin_guide_options.reference()


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def test_every_command_and_install_flag_is_in_the_guide() -> None:
    verbs = _subparsers(_parser())
    missing = [f"ospreyflow {verb}" for verb in verbs if f"ospreyflow {verb}" not in GUIDE]
    for verb in ("install", "doctor", "logs", "uninstall", "start"):
        for action in verbs[verb]._actions:
            missing += [flag for flag in action.option_strings
                        if flag.startswith("--") and flag != "--help" and flag not in GUIDE]  # fmt: skip
    missing += [f"demo {a}" for a in _subparsers(verbs["demo"]) if f"demo {a}" not in GUIDE]
    assert not missing, f"the guide never mentions: {', '.join(missing)}"


@pytest.mark.parametrize("key", sorted(_TOP))
def test_every_answers_file_setting_is_in_the_guide(key: str) -> None:
    keys = [key] if key not in _SECTIONS else [f"{key}.{child}" for child in _SECTIONS[key]]
    for name in keys:
        assert f"`{name}`" in GUIDE or f"{name}`" in GUIDE, f"{name} is not in the guide"
