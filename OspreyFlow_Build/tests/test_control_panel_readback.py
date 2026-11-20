"""The panel's last two guards (slice BL7, round 3): the one-line edit, and the read-back before the file is saved.

`tools/control_panel/panel.py` edits one line of a yaml file and keeps every other byte. Two guards stand behind that:

* `edit_text` refuses a file that does not have exactly one line for the key;
* `reads_back` (called in `apply_change`) refuses an edit that the scripts' own loader would read as something other than
  the one change asked for. The panel's docstring says "the file is replaced whole or not at all"; these are the cases
  that make that sentence a test (rule 12).

Pure, as `test_control_panel.py` is: the same fixtures (three synthetic yaml files in a temporary folder, a server on an
ephemeral loopback port), the same helpers. The shapes planted are the shapes the panel meets: a file the owner has
written by hand, a request in a POST body.

Rule 15. The first group refuses; the second removes the guard (`reads_back` always true) and shows the SAME request now
WRITES a file the scripts refuse, so the refusal cannot be coming from some other branch. `edit_text`'s own guard has no
second guard behind it that could hide it, so its cases call it directly and expect the refusal itself (a file with two
lines for a key would otherwise be caught by the read-back, which is why the server-level cases alone prove nothing about it).
"""
from __future__ import annotations

import pytest
import yaml

from tests.test_control_panel import (  # noqa: F401  (the fixtures are used by name)
    ACCOUNTS_YAML, DIAL_YAML, LIVE_STEP_YAML, assert_untouched, call, change, loaders, snapshot, w,
)
from tools.control_panel import panel

# A track the owner wrote as a block scalar: the line `  "1": |` looks like a one-line value to the line pattern, and the
# indented line below it is inside the section. Edited to `sol`, the file would read `sol default`.
BLOCK_TRACK = ACCOUNTS_YAML.replace('  "1": default\n', '  "1": |\n    default\n')
FOLDED_TRACK = ACCOUNTS_YAML.replace('  "1": default\n', '  "1": >-\n    default\n')
BLOCK_CURRENT = DIAL_YAML.replace("current: auto\n", "current: |\n  auto\n")
FLOW_TRACKS = ACCOUNTS_YAML.replace('  "1": default\n  "2": sol\n  "3": sol          # Sprint only\n'
                                    '  "4": sol              # Sprint only\n', "")\
    .replace("tracks:\n", 'tracks: {"1": default, "2": sol, "3": sol, "4": sol}\n')
ANCHORED_TRACK = ACCOUNTS_YAML.replace('  "1": default\n', '  "1": &a default\n')
TWICE_TRACK = ACCOUNTS_YAML.replace('  "2": sol\n', '  "2": sol\n  "1": default\n')
NO_SUCH_LINE_LIVE_STEP = LIVE_STEP_YAML.replace("live_step: false\n", "live_step:\n  false\n")

# (which file, its text, key, a valid new value) where the one-line edit produces a file that reads back differently
READS_BACK_WRONG = [
    ("accounts.yaml", BLOCK_TRACK, "accounts.tracks.1", "sol"),
    ("accounts.yaml", FOLDED_TRACK, "accounts.tracks.1", "sol"),
    ("dial.yaml", BLOCK_CURRENT, "dial.current", "sprint"),
]
# (which file, its text, key, a valid new value) where there is not exactly one line for the key
NOT_ONE_LINE = [
    ("accounts.yaml", FLOW_TRACKS, "accounts.tracks.1", "sol"),
    ("accounts.yaml", ANCHORED_TRACK, "accounts.tracks.1", "sol"),
    ("accounts.yaml", TWICE_TRACK, "accounts.tracks.1", "sol"),
    ("live_step.yaml", NO_SUCH_LINE_LIVE_STEP, "live_step", True),
]
IDS = ["block-track", "folded-track", "block-current"]


def plant(w, name, text):
    path = {"dial.yaml": w.cfg.dial_file, "accounts.yaml": w.cfg.accounts_file, "live_step.yaml": w.cfg.live_step_file}[name]
    path.write_text(text)
    return path


# ----------------------------------------------------------------------------- the read-back refuses what reads back wrong

@pytest.mark.parametrize("name,text,key,value", READS_BACK_WRONG, ids=IDS)
def test_the_plants_are_valid_files_a_valid_change_and_a_line_edit_that_matches(w, name, text, key, value):
    """The plants are real: the file loads, the value is one the validator accepts, and the line pattern DOES match, so
    the refusal below can only come from the read-back (a shape the one-line edit gets wrong, not one it declines)."""
    path = plant(w, name, text)
    docs = panel.read_docs(w.cfg)
    assert panel.validate_value(key, value, docs) == value
    file_key, which, edit_path = panel._file_and_path(w.cfg, key)
    assert file_key == path
    edited = panel.edit_text(text, edit_path, value)  # does not raise: the edit is made
    assert edited != text
    assert not panel.reads_back(yaml.safe_load(edited), docs[which], edit_path, value)


@pytest.mark.parametrize("name,text,key,value", READS_BACK_WRONG, ids=IDS)
def test_an_edit_that_reads_back_differently_is_refused_and_nothing_is_written(w, name, text, key, value):
    plant(w, name, text)
    before = snapshot(w)
    status, body = change(w, key, value)
    assert status == 500 and body["ok"] is False and "reads back" in body["refused"], (status, body)
    assert_untouched(w, before)


@pytest.mark.parametrize("name,text,key,value", READS_BACK_WRONG, ids=IDS)
def test_the_read_back_is_what_refuses_it_and_without_it_the_scripts_get_a_file_they_refuse(
        w, loaders, monkeypatch, name, text, key, value):
    """Rule 15: with the read-back removed, the same request is written, and the scripts' own loaders then misread it."""
    common, _ = loaders
    plant(w, name, text)
    monkeypatch.setattr(panel, "reads_back", lambda *a, **k: True)
    status, body = change(w, key, value)
    assert status == 200 and body["ok"], body
    if key == "accounts.tracks.1":
        got = common.account_for("builder", "1")
        assert got == "sol default"
        with pytest.raises(SystemExit):
            common.config_dir(got)
    else:
        dial = common.load_dial()
        assert dial["current"] == "sprint auto"
        assert dial["current"] not in ["auto", *dial["settings"]]
        assert common.current_setting(dial) == "balanced"  # the script falls back silently, to the day's setting


def test_the_read_back_also_refuses_a_value_that_reads_back_as_another_type():
    """The type half of the check: `1` and `True` are equal in Python, and a file that reads back `1` for a `true` is
    wrong. Planted as the loader's own output."""
    doc = {"live_step": False, "queue_wait_minutes": 60}
    assert panel.reads_back({"live_step": True, "queue_wait_minutes": 60}, doc, ("live_step",), True)
    assert not panel.reads_back({"live_step": 1, "queue_wait_minutes": 60}, doc, ("live_step",), True)
    assert not panel.reads_back({"live_step": True, "queue_wait_minutes": 61}, doc, ("live_step",), True)  # another key moved
    assert not panel.reads_back({"live_step": True}, doc, ("live_step",), True)                           # another key lost


# ------------------------------------------------------- the line edit refuses a file without exactly one line for the key

@pytest.mark.parametrize("name,text,key,value", NOT_ONE_LINE, ids=["flow", "anchor", "twice", "value-on-next-line"])
def test_a_file_without_exactly_one_line_for_the_key_is_refused_and_nothing_is_written(w, name, text, key, value):
    plant(w, name, text)
    docs = panel.read_docs(w.cfg)
    assert panel.validate_value(key, value, docs) == value  # the value is fine: it is the file's shape that is refused
    before = snapshot(w)
    status, body = change(w, key, value)
    assert status == 500 and body["ok"] is False and "cannot edit" in body["refused"], (status, body)
    assert_untouched(w, before)


@pytest.mark.parametrize("name,text,key,value", NOT_ONE_LINE, ids=["flow", "anchor", "twice", "value-on-next-line"])
def test_edit_text_itself_refuses_it(w, name, text, key, value):
    """Called directly, so that no later guard can be what refuses: with the one-line check removed, the file with the key
    twice is edited at its first line (and a file with no such line raises an IndexError, not this ValueError)."""
    _, _, path = panel._file_and_path(w.cfg, key)
    with pytest.raises(ValueError, match="not one"):
        panel.edit_text(text, path, value)


def test_edit_text_edits_one_line_and_only_one_in_the_files_as_written():
    """The converse, so the cases above are not refusing everything: the plain files are edited at exactly one line."""
    out = panel.edit_text(ACCOUNTS_YAML, ("tracks", "1"), "sol")
    assert [i for i, (a, b) in enumerate(zip(ACCOUNTS_YAML.splitlines(), out.splitlines())) if a != b] == [6]
    out = panel.edit_text(DIAL_YAML, ("current",), "sprint")
    assert out.replace("current: sprint", "current: auto") == DIAL_YAML
