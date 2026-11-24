"""The word check's "key" spares the known keyboard phrases, and only those (the owner, 24 November 2026).

The line never accepts, clears or sends back on its own a finding or stop that names a key, a credential or a
security rule (resume.SECURITY_WORDS, matched anywhere in a word). The owner's accept for PL8a was refused over "an
analyst's key press", the third keyboard false match. Now a list of known keyboard phrases is taken out of the words
first (resume.KEYBOARD_PHRASES): key press, keypress, keydown, keyup, keyboard, keyboard-only, the Home key, the End
key, arrow keys, the Enter, Escape or Tab key, key binding, key shortcut. Any other "key" still matches, so an
unknown use still stops; the credential, certificate and other words are not touched.
"""
from __future__ import annotations

import json

import pytest

from test_accept import TODAY, owner_line, rec, resume, said_refused, state, stopped_with_findings
from test_finding_kind import FAULT, GAP, finding
from test_gates import sh, world  # noqa: F401  (world is a fixture)

KEYBOARD = ["an analyst's key press does nothing on the map", "a keypress on the canvas is lost",
            "the keydown handler fires twice", "keyup is never heard", "the keyboard focus is lost",
            "the Home key goes nowhere", "the End key goes nowhere", "the arrow keys skip a row",
            "the Enter key submits twice", "the Escape key leaves the dialog open", "the Tab key skips the button",
            "the key binding is not shown", "the key shortcut is not listed", "the page is not keyboard-only usable",
            "KEYBOARD focus", "an analyst's Key Press"]
STILL = ["the engine key is logged", "the API key is shown back", "the access key leaks", "the provider key is sent",
         "key_name is printed", "a private key in the fixture", "the key is shown",
         "the keyboard shortcut prints the API key",                      # a phrase beside a real key
         "keyboard_secret is logged", "a keypad", "the monkey test", "key presser", "the monkey press release",
         "the session token survives a logout", "the certificate is not checked", "a credential in the log"]


def hits(w, texts):
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import resume as r; "
            f"print(json.dumps([bool(r.security_hit(t)) for t in json.loads(sys.argv[1])]))")
    return json.loads(sh([w["py"], "-c", code, json.dumps(texts)], w["repo"], w["env"]).stdout)


def test_each_known_keyboard_phrase_is_not_a_key(world):
    got = dict(zip(KEYBOARD, hits(world, KEYBOARD)))
    assert not any(got.values()), [t for t, h in got.items() if h]


def test_every_other_key_and_every_other_word_still_matches(world):
    got = dict(zip(STILL, hits(world, STILL)))
    assert all(got.values()), [t for t, h in got.items() if not h]


def test_pl8a_s_accept_over_a_key_press_applies(world):
    """PL8a, 24 November 2026: the owner's accept, refused over "an analyst's key press"."""
    w = world
    wt, tip = stopped_with_findings(w, findings=[finding(GAP, "no test for the empty list"),
                                                 finding(FAULT, "an analyst's key press on the map does nothing")])
    owner_line(w, f"S1\taccept\t{TODAY}")
    p = resume(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert state(w)["phase"] == "verified" and (rec(w) / f"accepted-{tip}.json").exists()


@pytest.mark.parametrize("what", ["the keyboard shortcut prints the API key", "the engine key is logged on a key press"],
                         ids=["shortcut-beside-api-key", "engine-key-beside-key-press"])
def test_a_real_key_beside_a_keyboard_phrase_is_still_refused(world, what):
    w = world
    stopped_with_findings(w, findings=[finding(GAP, "no test for the empty list"), finding(FAULT, what)])
    owner_line(w, f"S1\taccept\t{TODAY}")
    p = resume(w)
    assert said_refused(p, "key, a credential or a security rule"), p.stdout + p.stderr


def test_every_word_check_in_resume_goes_through_the_keyboard_phrases():
    """The owner's accept, the standing accept, round-after-refusal and the self-clear all read security_hit: no call
    site matches SECURITY_WORDS on its own (one that did would refuse a key press again)."""
    import re
    from test_gates import SRC
    text = (SRC / "resume.py").read_text()
    body = re.search(r"\ndef security_hit\(.*?\n(?=\S)", text, re.S).group(0)
    assert text.count("SECURITY_WORDS.search(") == body.count("SECURITY_WORDS.search(") == 1
    assert text.count("security_hit(") >= 5, text.count("security_hit(")       # its def and the four call sites
