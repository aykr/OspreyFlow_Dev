"""v0.6.0 is installed fresh, with no upgrade from any earlier version (the owner's plan of 15 November 2026, decision
2), and the guides say so where they say how a deployment moves to a release (rule 12):

- the CHANGELOG's v0.6.0 section says it in one plain sentence, and is the release `VERSION` names;
- the administration guide's §14 opens with it, §6a.1's *Moving to a new release* is for a release after v0.6.0,
  and the README's update table says it;
- no guide keeps a passage for a deployment only an earlier release could have made (the named-volume move, the
  rules' move at v0.5.0, an upgrade's egress, and the rest the rename struck).

`rf` (platform) makes `ospreyflow update`, an install over an existing deployment, and the cloud-platform
`INSTALL.md` refuse an earlier one in words, from `harness.fresh_only.refusal`; §14 quotes them, held here.
"""

from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
FRESH = "**v0.6.0 is installed fresh: there is no upgrade to it from any earlier version.**"
#: What the guides said for a deployment made by an earlier release, before v0.6.0 was installed fresh only.
OLD_RELEASE_PASSAGES = (
    "every install before v0.4.2",
    "An `admin` made by v0.4.6",
    "**After updating to v0.5.0",
    "After upgrading from a release before",
    "loaded it before v0.2.0",
    "installed with v0.4.10 or earlier",
    "An `osprey.yaml` from v0.4.x",
    "Sets taken before v0.5.0",
    "v0.4.8 and earlier on Linux",
    "Linux, v0.4.8 or earlier",
    "A bundle made before v0.4.12",
    "one-time move to named volumes",
    "### 14.1 Removing the old store volumes",
    "updated to the release after v0.4.10",
    "From the release after v0.4.10",
    "an index made before v0.5.2",
    "install v0.5.1, then the candidate",
)


def prose(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", " ", text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", text)


def old_release_passages(texts: dict[str, str]) -> list[str]:
    return [f"{name}: {old!r}" for name, text in texts.items() for old in OLD_RELEASE_PASSAGES if old in text]


def guides() -> dict[str, str]:
    found = {g: prose(CORE / "docs" / f"{g}-guide.md") for g in ("user", "administration", "developer", "architecture")}
    found["readme"] = prose(CORE / "README.md")
    found["demo"] = prose(CORE / "DEMO_GUIDE.md")
    return found


def test_the_changelog_says_v060_is_installed_fresh_and_version_names_it() -> None:
    assert (CORE / "VERSION").read_text(encoding="utf-8").strip() == "v0.6.0"
    log = (CORE / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## (v\d+\.\d+\.\d+) — \d{4}-\d{2}-\d{2}$", log, re.MULTILINE)
    assert m and m.group(1) == "v0.6.0", "the latest release in the CHANGELOG"
    section = log[m.end() : log.index("\n## ", m.end())]
    assert section.lstrip().startswith(FRESH), "the sentence first, in the section's own words"
    assert "**Before you install.**" in section and "**Before you update.**" not in section
    assert "## v0.5.2" not in log, "v0.5.2 is never published"


def test_the_guides_say_how_a_v060_deployment_moves_and_that_v060_is_installed_fresh() -> None:
    text = guides()
    admin = text["administration"]
    fourteen = admin[admin.index("## 14. Updates") : admin.index("**Which installs `update` moves")]
    assert ("**v0.6.0 is installed fresh.** No earlier deployment is moved to it: a deployment made by an earlier "
            "release stays on that release, and v0.6.0 is installed as a new deployment.") in fourteen  # fmt: skip
    assert "v0.6.0 itself is installed fresh, into a namespace of its own" in admin
    assert ("v0.6.0 itself is installed fresh: no earlier deployment is moved to it, and what follows is how a v0.6.0 "
            "deployment moves to a later release.") in text["readme"]  # fmt: skip


def test_no_guide_keeps_a_passage_for_an_earlier_release_s_deployment() -> None:
    assert old_release_passages(guides()) == []


def test_an_earlier_release_s_passage_is_flagged() -> None:
    """The administration guide's own words before the rename (§13, §14)."""
    planted = {"administration": "**The stores' one-time move to named volumes.** A deployment installed with v0.4.10 or "
               "earlier keeps its PostgreSQL. Sets taken before v0.5.0 may still be in the checkout's `backups/`."}  # fmt: skip
    assert old_release_passages(planted) == [
        "administration: 'installed with v0.4.10 or earlier'", "administration: 'Sets taken before v0.5.0'",
        "administration: 'one-time move to named volumes'"]  # fmt: skip


def test_section_14_quotes_the_refusal_as_harness_fresh_only_words_it() -> None:
    import sys

    sys.path.insert(0, str(CORE))
    try:
        from harness import fresh_only
    except ImportError as missing:  # never a skip: the guide quotes words only this module holds
        raise AssertionError("harness.fresh_only (platform's rf) is not here, so §14's quotation holds to nothing") from missing
    assert fresh_only.FRESH_FROM == "v0.6.0"
    said = re.sub(r"\s+", " ", fresh_only.refusal("v0.5.2", "v0.6.0")).replace("v0.5.2", "‹release›")
    assert said.startswith("v0.6.0 is installed fresh;")
    admin = guides()["administration"]
    assert f'refuse an earlier one before anything is changed: "{said}"' in admin
