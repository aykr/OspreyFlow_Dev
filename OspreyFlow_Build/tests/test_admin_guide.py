"""The administration guide describes what is built, all of it — both copies: the specification's
(`spec/10_ADMINISTRATION_GUIDE.md`) and the install package's (`docs/administration-guide.md`, ADR-114
Amendment 15 point 5), so the two cannot drift from the product or from each other.

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

GUIDES = {path.name: path.read_text(encoding="utf-8") for path in admin_guide_options.GUIDES}
each_guide = pytest.mark.parametrize("name", sorted(GUIDES))


@each_guide
def test_the_settings_appendix_is_the_schemas_own(name: str) -> None:
    assert admin_guide_options.guide_copy(GUIDES[name]) == admin_guide_options.reference(), (
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


@each_guide
def test_every_command_and_install_flag_is_in_the_guide(name: str) -> None:
    GUIDE = GUIDES[name]
    verbs = _subparsers(_parser())
    missing = [f"ospreyflow {verb}" for verb in verbs if f"ospreyflow {verb}" not in GUIDE]
    for verb in ("install", "doctor", "logs", "uninstall", "start"):
        for action in verbs[verb]._actions:
            missing += [flag for flag in action.option_strings
                        if flag.startswith("--") and flag != "--help" and flag not in GUIDE]  # fmt: skip
    missing += [f"demo {a}" for a in _subparsers(verbs["demo"]) if f"demo {a}" not in GUIDE]
    assert not missing, f"the guide never mentions: {', '.join(missing)}"


@each_guide
@pytest.mark.parametrize("key", sorted(_TOP))
def test_every_answers_file_setting_is_in_the_guide(name: str, key: str) -> None:
    GUIDE = GUIDES[name]
    keys = [key] if key not in _SECTIONS else [f"{key}.{child}" for child in _SECTIONS[key]]
    for setting in keys:
        assert f"`{setting}`" in GUIDE or f"{setting}`" in GUIDE, f"{setting} is not in {name}"
