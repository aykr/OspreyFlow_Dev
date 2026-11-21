"""The register's gate leg, from the other side: what `python -m tools.licence_check` (which `make
licence-check` and ci.yml run) does when the code and the register part (PL11 item 5).

These sit beside the frozen acceptance file `test_register.py` and each plants its fault in the real
text the leg reads, never a hand-written stand-in (rule 15).

**The folders this test walks:** none of its own. It reads what
`tools.licence_register.read_sources` reads (under `OspreyFlow_Core`: `harness/*.py`,
`providers/*.yaml`, `Dockerfile*` found under the whole of `OspreyFlow_Core/` and the named files
in that module's docstring) and the register.
"""

from __future__ import annotations

from typing import Any

import pytest
from tools import licence_register as reg


def _violations(sources: dict[str, str]) -> list[str]:
    return reg.find_register_violations(reg.load_register(), reg.named_by_code(sources))


def test_a_pull_script_and_a_closed_list_that_disagree_on_a_pin_are_flagged() -> None:
    """The embeddings model is named twice (the pull script and `EMBEDDING_MODELS`): change one and
    the code names two pins for it, and the register can hold only one of them. The message says the
    pin differs, names the one that is not registered and the one that is."""
    sources = dict(reg.read_sources())
    text = sources["harness/render.py"]
    old = "pull_and_verify all-minilm:22m-l6-v2-fp16 1b226e2802db"
    changed = text.replace(old, "pull_and_verify all-minilm:22m-l6-v2-fp16 ffffffffffff")
    assert changed != text
    sources["harness/render.py"] = changed
    found = _violations(sources)
    assert any(
        "all-minilm" in v
        and "pin differs" in v
        and "ffffffffffff" in v
        and "not in the register" in v
        and "1b226e2802db" in v
        for v in found
    ), found


def test_the_gate_leg_reaches_main_and_main_fails_naming_a_planted_image(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Plant a new `FROM` in the sources the leg reads and the run exits 1 and names it, where with
    the real sources it exits 0 (the other legs are given no packages so only this one can fail)."""
    from tools import licence_check

    monkeypatch.setattr(licence_check, "run_pip_licenses", lambda extra: [])
    monkeypatch.setattr("sys.argv", ["licence_check"])
    assert licence_check.main() == 0
    assert "the licence register agrees with the code" in capsys.readouterr().out

    real = reg.read_sources()
    planted: dict[str, Any] = {
        **real,
        "services/ner/Dockerfile": real["services/ner/Dockerfile"] + "\nFROM alpine:3.21\n",
    }
    monkeypatch.setattr(reg, "read_sources", lambda *a, **k: planted)
    assert licence_check.main() == 1
    assert "alpine" in capsys.readouterr().err
