"""The owner's control panel (slice BL7; decisions D24-D26 of 18 November 2026): `tools/control_panel/`.

A local server on 127.0.0.1 that saves the owner's changes to the three yaml files the slice line's scripts read (the
dial, the accounts, the live step) and a stored, unread switch for automatic balancing; it refuses any Host but its own,
any request without its token, and any value the scripts would silently fall back from; it logs every change.

Pure: a server on an ephemeral loopback port, in a temporary folder. No other address is opened, no store is reached.

Rule 15, for every refusal below: the request is planted in the shape the server receives it (a raw Host header, a raw
Authorization header, a raw body), and a second case removes the check under test and shows the same request now WRITES,
so the first case cannot be passing because some other branch happened to refuse it.
"""
from __future__ import annotations

import http.client
import importlib
import json
import re
import shutil
import stat
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from tools.control_panel import panel

BUILD = Path(__file__).resolve().parents[1]
V062 = BUILD / "process" / "lanes" / "v062"
LINE = BUILD / "scripts" / "slice_line"
DEFAULT = object()


# --------------------------------------------------------------------------------------------------------- the world

@dataclass
class World:
    cfg: panel.Config
    token: str
    port: int


@pytest.fixture
def w(tmp_path):
    """The three real yaml files (comments and all), copied; a data folder; a token; a server on an ephemeral port."""
    lane = tmp_path / "lane"
    lane.mkdir()
    for name in ("dial.yaml", "accounts.yaml", "live_step.yaml"):
        shutil.copy(V062 / name, lane / name)
    data = tmp_path / "data"
    data.mkdir()
    token_file = tmp_path / "secret" / "token"
    token = panel.ensure_token(token_file)
    cfg = panel.Config(dial_file=lane / "dial.yaml", accounts_file=lane / "accounts.yaml",
                       live_step_file=lane / "live_step.yaml", data_dir=data, token_file=token_file)
    server = panel.make_server(cfg, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield World(cfg, token, server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)


@pytest.fixture
def loaders(w, monkeypatch):
    """The scripts' own loaders, loaded from their files and pointed at the world's copies of the three files."""
    names = ("common", "owed", "scan_select", "merge_slice")
    saved = {n: sys.modules.pop(n, None) for n in names}
    monkeypatch.syspath_prepend(str(LINE))
    try:
        common = importlib.import_module("common")
        merge_slice = importlib.import_module("merge_slice")
        monkeypatch.setattr(common, "DIAL_FILE", w.cfg.dial_file)
        monkeypatch.setattr(common, "ACCOUNTS_FILE", w.cfg.accounts_file)
        monkeypatch.setattr(merge_slice, "LIVE_STEP_FILE", w.cfg.live_step_file)
        yield common, merge_slice
    finally:
        for n in names:
            sys.modules.pop(n, None)
            if saved[n] is not None:
                sys.modules[n] = saved[n]


def call(w, method, path, body=None, *, host=DEFAULT, auth=DEFAULT, raw=None, headers=None):
    """One request, sent as a client would send it. `host`/`auth` None leaves the header out; a string is sent as it is
    ('{port}' and '{token}' filled in)."""
    conn = http.client.HTTPConnection("127.0.0.1", w.port, timeout=10)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        host = f"127.0.0.1:{w.port}" if host is DEFAULT else host
        if host is not None:
            conn.putheader("Host", host.replace("{port}", str(w.port)))
        auth = "Bearer {token}" if auth is DEFAULT else auth
        if auth is not None:
            conn.putheader("Authorization", auth.replace("{token}", w.token))
        for k, v in (headers or {}).items():
            conn.putheader(k, v)
        payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
        if method == "POST":
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(payload)))
        conn.endheaders(payload if method == "POST" else None)
        resp = conn.getresponse()
        text = resp.read().decode("utf-8", "replace")
        try:
            return resp.status, json.loads(text)
        except ValueError:
            return resp.status, text
    finally:
        conn.close()


def change(w, key, value, **kw):
    return call(w, "POST", "/api/change", {"key": key, "value": value}, **kw)


def files(w):
    c = w.cfg
    return (c.dial_file, c.accounts_file, c.live_step_file)


def snapshot(w):
    """Every byte the panel could write: the three files, the change log, the settings file (None = not there)."""
    c = w.cfg
    paths = (*files(w), c.data_dir / panel.CHANGES_LOG, c.data_dir / panel.SETTINGS_FILE)
    return {p.name: (p.read_bytes() if p.exists() else None) for p in paths}


def log_rows(w):
    f = w.cfg.data_dir / panel.CHANGES_LOG
    if not f.exists():
        return []
    lines = f.read_text().splitlines()
    assert lines[0] == "at\tkey\told\tnew", lines[0]
    return [dict(zip(("at", "key", "old", "new"), ln.split("\t"))) for ln in lines[1:]]


def read_back(loaders, key):
    """What the scripts' own loaders say a key is."""
    common, merge_slice = loaders
    parts = key.split(".")
    if parts[0] == "dial":
        return common.load_dial()[parts[1]]
    if parts[:2] == ["accounts", "seats"]:
        return common.account_for(parts[2])
    if parts[:2] == ["accounts", "tracks"]:
        return common.account_for("builder", parts[2])
    assert key == "live_step", key
    return merge_slice.live_step_setting()[0]


def differing_lines(before: bytes, after: bytes) -> list[int]:
    a, b = before.decode().splitlines(), after.decode().splitlines()
    assert len(a) == len(b), "a change added or removed a line"
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]


# What the real files hold today: current auto; conductor/scout default, verifier sol; tracks 1 default, 2-4 sol;
# live_step false. Each pair below differs from that, so each is a real change.
VALID = [
    ("dial.current", "sprint"), ("dial.current", "thrift"), ("dial.current", "balanced"),
    ("dial.day", "thrift"), ("dial.night", "sprint"),
    ("accounts.seats.verifier", "default"), ("accounts.seats.conductor", "sol"), ("accounts.seats.scout", "sol"),
    ("accounts.tracks.1", "sol"), ("accounts.tracks.3", "default"), ("accounts.tracks.4", "default"),
    ("accounts.tracks.2", "a-b2"),
    # names the YAML 1.1 loader would read as something else if written bare: the scripts must still get a string
    ("accounts.tracks.1", "no"), ("accounts.tracks.1", "on"), ("accounts.tracks.1", "null"), ("accounts.tracks.1", "true"),
    ("live_step", True),
]

INVALID = [
    ("dial.current", "turbo"), ("dial.current", "SPRINT"), ("dial.current", " sprint"), ("dial.current", ""),
    ("dial.current", 5), ("dial.current", None), ("dial.current", True), ("dial.current", ["sprint"]),
    ("dial.current", {"a": 1}), ("dial.current", "sprint\nday: thrift"), ("dial.current", "sprint # x"),
    ("dial.day", "auto"), ("dial.day", "turbo"), ("dial.night", "nope"), ("dial.night", 3),
    ("accounts.seats.verifier", "Sol"), ("accounts.seats.verifier", "sol "), ("accounts.seats.verifier", ""),
    ("accounts.seats.verifier", "../etc"), ("accounts.seats.verifier", "1sol"), ("accounts.seats.verifier", "sol_x"),
    ("accounts.seats.verifier", "sol\nconductor: x"), ("accounts.seats.verifier", "sol # x"),
    ("accounts.seats.verifier", 5), ("accounts.seats.verifier", True), ("accounts.seats.verifier", None),
    ("accounts.seats.verifier", ["sol"]), ("accounts.tracks.1", "x y"), ("accounts.tracks.1", "-sol"),
    ("accounts.tracks.1", "a" * 65),
    ("accounts.tracks.9", "sol"), ("accounts.seats.janitor", "sol"), ("accounts.tracks.1.x", "sol"),
    ("accounts.seats", "sol"), ("accounts.tracks", "sol"), ("accounts", "sol"), ("dial", "sprint"),
    ("dial.settings", "sprint"), ("dial.day_hours", "sprint"),
    ("live_step", "true"), ("live_step", "false"), ("live_step", "yes"), ("live_step", 1), ("live_step", 0),
    ("live_step", None), ("live_step", [True]),
    ("balancing", "on"), ("balancing", 1), ("balancing", None),
    ("queue_wait_minutes", 5), ("", "x"), ("dial.current ", "sprint"), (5, "sprint"), (None, "sprint"),
]


def assert_untouched(w, before):
    assert snapshot(w) == before


# --------------------------------------------------------------------------------- bound to the Mac and nothing else

@pytest.mark.parametrize("host", ["0.0.0.0", "", "localhost", "::", "::1", "192.168.1.20", "10.0.0.4", "example.com"])
def test_the_server_binds_127_0_0_1_only_and_refuses_to_open_any_other_address(w, host):
    with pytest.raises(ValueError):
        panel.make_server(w.cfg, host=host, port=0)


def test_the_running_server_is_on_127_0_0_1(w):
    server = panel.make_server(w.cfg, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_the_command_line_has_no_way_to_name_another_address_and_touches_nothing_first(tmp_path, monkeypatch):
    """The refusal comes before anything is made: no token, no folder. (The defaults are pointed at a scratch folder, so a
    broken check here cannot make a real token in the owner's home.)"""
    monkeypatch.setattr(panel, "DEFAULT_TOKEN_FILE", tmp_path / "home" / "token")
    monkeypatch.setattr(panel, "DEFAULT_DATA_DIR", tmp_path / "home" / "data")
    assert panel.main(["--host", "0.0.0.0", "--port", "0"]) == 2
    assert not (tmp_path / "home").exists()


# ---------------------------------------------------------------------------------------------- the Host is checked

REFUSED_HOSTS = [
    "evil.example", "evil.example:{port}", "192.168.1.20:{port}", "0.0.0.0:{port}", "127.0.0.1.evil.example:{port}",
    "localhost.evil.example:{port}", "[::1]:{port}", "127.0.0.1:1", "127.0.0.1:{port}x", "127.0.0.1", "", None,
    "127.0.0.1:{port}, evil.example", "LOCALHOST.evil.example:{port}", "127.1:{port}", "2130706433:{port}",
]


@pytest.mark.parametrize("host", REFUSED_HOSTS)
def test_a_request_from_a_non_loopback_host_is_refused_writes_nothing_even_with_the_right_token(w, host):
    before = snapshot(w)
    status, _ = change(w, "dial.current", "sprint", host=host)
    assert status == 403
    status, _ = call(w, "GET", "/api/state", host=host)
    assert status == 403
    assert_untouched(w, before)


@pytest.mark.parametrize("host", ["127.0.0.1:{port}", "localhost:{port}", "LocalHost:{port}"])
def test_the_panels_own_names_are_let_through(w, host):
    status, _ = call(w, "GET", "/api/state", host=host)
    assert status == 200


def test_the_host_refusal_is_the_host_checks_own(w, monkeypatch):
    """Rule 15: with the Host check removed, the planted request (a foreign Host, a right token, a valid change) writes."""
    monkeypatch.setattr(panel, "host_allowed", lambda *a, **k: True)
    before = snapshot(w)
    status, body = change(w, "dial.current", "sprint", host="evil.example")
    assert status == 200 and body["ok"], body
    assert snapshot(w) != before


# --------------------------------------------------------------------------------------------- the token is checked

REFUSED_AUTH = [
    None,                          # no header at all
    "",                            # an empty header
    "Bearer ",                     # a scheme with nothing after it
    "Bearer wrong-token-of-a-plausible-length-0123456789",
    "Bearer {token}x",             # the right token, longer
    "Bearer {token}\u00a0",
    "Bearer {tokenhead}",          # the right token's first half
    "{token}",                     # the right token with no scheme
    "Token {token}",               # the right token under another scheme
    "Basic {token}",
    "bearer-{token}",
]


def planted_auth(w, auth):
    return None if auth is None else auth.replace("{tokenhead}", w.token[: len(w.token) // 2])


@pytest.mark.parametrize("auth", REFUSED_AUTH)
def test_a_request_with_no_token_or_a_wrong_one_is_refused_and_writes_nothing(w, auth):
    before = snapshot(w)
    status, _ = change(w, "dial.current", "sprint", auth=planted_auth(w, auth))
    assert status == 401
    status, body = call(w, "GET", "/api/state", auth=planted_auth(w, auth))
    assert status == 401 and w.token not in json.dumps(body)
    assert_untouched(w, before)


def test_the_token_in_the_address_or_the_body_is_not_a_token(w):
    before = snapshot(w)
    status, _ = call(w, "POST", f"/api/change?token={w.token}", {"key": "dial.current", "value": "sprint"}, auth=None)
    assert status == 401
    status, _ = call(w, "POST", "/api/change", {"key": "dial.current", "value": "sprint", "token": w.token}, auth=None)
    assert status == 401
    status, _ = call(w, "GET", f"/api/state?token={w.token}", auth=None)
    assert status == 401
    status, _ = call(w, "GET", "/api/state", auth=None, headers={"X-Panel-Token": w.token, "Cookie": f"token={w.token}"})
    assert status == 401
    assert_untouched(w, before)


def test_the_token_refusal_is_the_token_checks_own(w, monkeypatch):
    """Rule 15: with the token check removed, the planted request (no token, a valid change) writes."""
    monkeypatch.setattr(panel, "token_ok", lambda *a, **k: True)
    before = snapshot(w)
    status, body = change(w, "dial.current", "sprint", auth=None)
    assert status == 200 and body["ok"], body
    assert snapshot(w) != before


def test_the_host_is_checked_before_the_token_and_the_token_before_the_body(w):
    """A foreign Host with no token says 403 (it learns nothing about tokens); no token with a nonsense body says 401."""
    assert change(w, "dial.current", "sprint", host="evil.example", auth=None)[0] == 403
    assert call(w, "POST", "/api/change", raw=b"not json", auth=None)[0] == 401


# --------------------------------------------------------------------------- a valid change is written and is logged

@pytest.mark.parametrize("key,value", VALID)
def test_a_valid_change_is_written_logged_and_read_back_by_the_scripts_own_loaders(w, loaders, key, value):
    old_read = read_back(loaders, key)
    before = snapshot(w)
    docs_before = [yaml.safe_load(p.read_text()) for p in files(w)]
    status, body = change(w, key, value)
    assert status == 200 and body["ok"] is True, body
    assert body["key"] == key and body["new"] == value and body["old"] == old_read, body

    assert read_back(loaders, key) == value
    assert type(read_back(loaders, key)) is type(value)
    if isinstance(value, str) and key.startswith("accounts."):
        loaders[0].config_dir(value)  # the scripts accept it as an account (they exit on a name they refuse)

    after = snapshot(w)
    changed = [n for n in before if before[n] != after[n]]
    target = {"dial": "dial.yaml", "accounts": "accounts.yaml", "live_step": "live_step.yaml"}[key.split(".")[0]]
    assert changed == [target, panel.CHANGES_LOG], changed
    assert len(differing_lines(before[target], after[target])) == 1  # one line, nothing else touched
    # every other thing in every file reads as before
    docs_after = [yaml.safe_load(p.read_text()) for p in files(w)]
    expected = json.loads(json.dumps(docs_before))
    node = expected[("dial", "accounts", "live_step").index(key.split(".")[0])]
    parts = key.split(".")[1:] or [key]
    for p in parts[:-1]:
        node = node[p]
    node[parts[-1]] = value
    assert docs_after == expected

    rows = log_rows(w)
    assert len(rows) == 1
    assert rows[0]["key"] == key
    assert json.loads(rows[0]["old"]) == old_read and json.loads(rows[0]["new"]) == value
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", rows[0]["at"]), rows[0]["at"]
    assert w.token not in (w.cfg.data_dir / panel.CHANGES_LOG).read_text()


def test_the_owners_comments_and_the_rest_of_each_line_survive_a_change(w):
    before = w.cfg.accounts_file.read_text()
    assert "# Sprint only" in before
    assert change(w, "accounts.tracks.4", "default")[0] == 200
    after = w.cfg.accounts_file.read_text()
    line = next(ln for ln in after.splitlines() if ln.lstrip().startswith('"4"'))
    assert line.endswith("# Sprint only") and "default" in line
    assert [ln for ln in before.splitlines() if ln.lstrip().startswith("#")] == \
           [ln for ln in after.splitlines() if ln.lstrip().startswith("#")]
    before = w.cfg.live_step_file.read_text()
    assert change(w, "live_step", True)[0] == 200
    after = w.cfg.live_step_file.read_text()
    assert [ln for ln in before.splitlines() if ln.startswith("#")] == [ln for ln in after.splitlines() if ln.startswith("#")]
    assert yaml.safe_load(after)["live_step"] is True


def test_changes_are_appended_in_order_and_an_unchanged_value_is_neither_written_nor_logged(w):
    assert change(w, "dial.current", "sprint")[0] == 200
    assert change(w, "dial.current", "thrift")[0] == 200
    before = snapshot(w)
    status, body = change(w, "dial.current", "thrift")
    assert status == 200 and body["ok"] and body["changed"] is False
    assert_untouched(w, before)
    rows = log_rows(w)
    assert [(r["key"], json.loads(r["old"]), json.loads(r["new"])) for r in rows] == [
        ("dial.current", "auto", "sprint"), ("dial.current", "sprint", "thrift")]


def test_a_change_the_log_cannot_record_is_not_left_in_the_file(w, tmp_path):
    (w.cfg.data_dir / panel.CHANGES_LOG).mkdir()  # a log that cannot be appended to
    before = {p.name: p.read_bytes() for p in files(w)}
    status, body = change(w, "dial.current", "sprint")
    assert status == 500 and body["ok"] is False
    assert {p.name: p.read_bytes() for p in files(w)} == before


# ----------------------------------------------------------------- an invalid value is refused; the file is untouched

@pytest.mark.parametrize("key,value", INVALID, ids=[f"{k!r}={v!r}"[:60] for k, v in INVALID])
def test_an_invalid_change_is_refused_and_every_file_is_byte_identical_afterwards(w, key, value):
    before = snapshot(w)
    status, body = call(w, "POST", "/api/change", {"key": key, "value": value})
    assert status == 400 and body["ok"] is False and body["refused"], (status, body)
    assert_untouched(w, before)


@pytest.mark.parametrize("raw,headers", [
    (b"not json", None), (b"", None), (b"[]", None), (b'"dial.current"', None), (b"null", None),
    (b'{"key": "dial.current"}', None), (b'{"value": "sprint"}', None),
    (b'{"key": "dial.current", "value": "sprint", "also": 1}', None),
    (b'{"key": "dial.current", "value": "sprint"} trailing', None),
    (b'{"key": "dial.current", "value": "sprint", "value": "x"}', None),
    (b'{"key": "dial.current", "value": NaN}', None),
    ('{"key": "dial.current", "value": "spr\u00ednt"}'.encode(), None),
    (b'\xff\xfe{"key": "dial.current", "value": "sprint"}', None),
])
def test_a_malformed_body_is_refused_and_writes_nothing(w, raw, headers):
    before = snapshot(w)
    status, body = call(w, "POST", "/api/change", raw=raw)
    assert status == 400 and body["ok"] is False
    assert_untouched(w, before)


def test_the_validation_is_what_refuses_an_invalid_value(w, loaders, monkeypatch):
    """Rule 15: with the value check removed, each planted value is written, and the scripts then misread or refuse it
    (the settings the panel must never write). Each is the shape the server receives: a JSON value in a POST body."""
    monkeypatch.setattr(panel, "validate_value", lambda key, value, docs: value)
    common, merge_slice = loaders
    assert change(w, "dial.current", "turbo")[0] == 200
    dial = common.load_dial()
    assert dial["current"] == "turbo"
    assert common.current_setting(dial) in dial["settings"]  # the script falls back silently to day or night
    assert change(w, "accounts.tracks.1", "Sol X")[0] == 200
    with pytest.raises(SystemExit):
        common.config_dir(common.account_for("builder", "1"))
    assert change(w, "live_step", "maybe")[0] == 200
    with pytest.raises(merge_slice.GateEnvError):
        merge_slice.live_step_setting()


# ------------------------------------------------------------------------------ the size of what the server will read

def test_a_body_over_the_cap_is_refused_unread_and_writes_nothing(w):
    before = snapshot(w)
    body = json.dumps({"key": "dial.current", "value": "sprint"}).encode() + b" " * (panel.MAX_BODY * 4)
    status, resp = call(w, "POST", "/api/change", raw=body)
    assert status == 413 and resp["ok"] is False
    assert_untouched(w, before)


def test_the_size_cap_is_what_refuses_an_over_long_body(w, monkeypatch):
    """Rule 15: the planted body is a VALID change padded with spaces, so only the cap can refuse it."""
    body = json.dumps({"key": "dial.current", "value": "sprint"}).encode() + b" " * (panel.MAX_BODY * 4)
    monkeypatch.setattr(panel, "MAX_BODY", len(body) + 1)
    status, resp = call(w, "POST", "/api/change", raw=body)
    assert status == 200 and resp["ok"], resp


def test_a_path_the_panel_does_not_have_and_a_method_it_does_not_take(w):
    before = snapshot(w)
    assert call(w, "GET", "/")[0] == 404
    assert call(w, "GET", "/../../etc/passwd")[0] == 404
    assert call(w, "GET", "/api/change")[0] == 405
    assert call(w, "POST", "/api/state", {})[0] == 405
    assert call(w, "PUT", "/api/change", {"key": "dial.current", "value": "sprint"})[0] in (405, 501)
    assert call(w, "DELETE", "/api/change")[0] in (405, 501)
    assert_untouched(w, before)


# ------------------------------------------------------------------------------------- the balancing switch is stored

def test_the_balancing_switch_is_off_by_default_and_stored_when_turned_on(w):
    status, state = call(w, "GET", "/api/state")
    assert status == 200 and state["balancing"] is False
    assert not (w.cfg.data_dir / panel.SETTINGS_FILE).exists()
    yaml_before = {p.name: p.read_bytes() for p in files(w)}

    status, body = change(w, "balancing", True)
    assert status == 200 and body["ok"] and body["old"] is False and body["new"] is True
    assert call(w, "GET", "/api/state")[1]["balancing"] is True
    assert json.loads((w.cfg.data_dir / panel.SETTINGS_FILE).read_text()) == {"balancing": True}
    assert {p.name: p.read_bytes() for p in files(w)} == yaml_before  # nothing in the three files: nothing reads it yet
    rows = log_rows(w)
    assert [(r["key"], r["old"], r["new"]) for r in rows] == [("balancing", "false", "true")]

    assert change(w, "balancing", False)[0] == 200
    assert call(w, "GET", "/api/state")[1]["balancing"] is False


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"balancing": "yes"}', '{"balancing": 1}', '{"balancing": null}',
                                     '{"other": true}', "\x00", '{"balancing": true'])
def test_a_settings_file_that_does_not_plainly_say_true_means_off(w, content):
    (w.cfg.data_dir / panel.SETTINGS_FILE).write_text(content)
    assert call(w, "GET", "/api/state")[1]["balancing"] is False


def test_no_script_reads_the_balancing_switch_yet(loaders):
    """The brief: a stored setting only. The scripts under the slice line do not name it, so turning it on changes nothing."""
    text = "".join(p.read_text() for p in LINE.glob("*.py"))
    assert panel.SETTINGS_FILE not in text and "control-panel" not in text


# --------------------------------------------------------------------------- what each account has used, and no guess

def write_account(w, account, windows):
    d = w.cfg.data_dir / "accounts"
    d.mkdir(exist_ok=True)
    (d / f"{account}.json").write_text(json.dumps({"windows": windows}, allow_nan=True))


def test_each_accounts_windows_are_shown_beside_it_and_a_missing_figure_says_so(w):
    write_account(w, "sol", {"five_hour": {"utilization": 0.31, "resetsAt": 4102444800},
                             "seven_day": {"utilization": 0.32, "resetsAt": 4102444800}})
    write_account(w, "default", {"seven_day": {"utilization": 0.07}})
    status, state = call(w, "GET", "/api/state")
    assert status == 200
    sol, default = state["usage"]["sol"]["windows"], state["usage"]["default"]["windows"]
    assert sol["five_hour"] == {"utilisation": 0.31, "text": "31%"}
    assert sol["seven_day"] == {"utilisation": 0.32, "text": "32%"}
    assert default["seven_day"]["text"] == "7%"
    assert default["five_hour"] == {"utilisation": None, "text": "no figure"}  # the key is not there: no guess
    assert set(state["usage"]) >= {"default", "sol"}  # every account the accounts file names


@pytest.mark.parametrize("figure", ["0.5", True, False, None, 7, -0.1, 1.01, float("nan"), float("inf"), [0.2], {"a": 1}])
def test_a_figure_that_is_not_a_share_between_nought_and_one_says_no_figure(w, figure):
    write_account(w, "sol", {"five_hour": {"utilization": figure}, "seven_day": {"utilization": 0.4}})
    sol = call(w, "GET", "/api/state")[1]["usage"]["sol"]["windows"]
    assert sol["five_hour"] == {"utilisation": None, "text": "no figure"}
    assert sol["seven_day"]["text"] == "40%"


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"windows": []}', '{"windows": {"five_hour": 3}}',
                                     '{"windows": {"five_hour": null}}', "{}"])
def test_an_account_file_that_cannot_be_read_says_no_figure_for_both_windows(w, content):
    d = w.cfg.data_dir / "accounts"
    d.mkdir()
    (d / "sol.json").write_text(content)
    sol = call(w, "GET", "/api/state")[1]["usage"]["sol"]["windows"]
    assert sol["five_hour"]["text"] == "no figure" and sol["seven_day"]["text"] == "no figure"


USAGE_HEADER = ("at\tslice\tbuild\tseat\taccount\tmodel\teffort\tsession\tinput\tcache_create\tcache_read\toutput\tcost_usd\t"
                "five_hour\tseven_day\n")


def usage_row(account, slice_id="BL7", seat="builder", inp=10, cc=5, cr=100, out=7):
    return "\t".join(["2026-11-19T06:00:00Z", slice_id, slice_id, seat, account, "sonnet", "high", "s1",
                      str(inp), str(cc), str(cr), str(out), "", "0.2", "0.3"]) + "\n"


def test_usage_totals_per_account_come_from_usage_tsv_and_a_bad_row_is_skipped(w):
    (w.cfg.data_dir / "usage.tsv").write_text(
        USAGE_HEADER + usage_row("sol") + usage_row("sol", inp=20, out=3) + usage_row("default", inp=1, cc=1, cr=1, out=1)
        + "garbage\n" + usage_row("sol", inp=0).replace("\t0\t", "\tNaN-not-a-number\t", 1))
    usage = call(w, "GET", "/api/state")[1]["usage"]
    assert usage["sol"]["totals"] == {"sessions": 2, "input": 30, "cache_create": 10, "cache_read": 200, "output": 10}
    assert usage["default"]["totals"] == {"sessions": 1, "input": 1, "cache_create": 1, "cache_read": 1, "output": 1}


def test_an_account_with_no_usage_has_zero_totals_not_a_missing_entry(w):
    usage = call(w, "GET", "/api/state")[1]["usage"]
    assert usage["sol"]["totals"] == {"sessions": 0, "input": 0, "cache_create": 0, "cache_read": 0, "output": 0}


def test_the_state_shows_the_dial_the_accounts_the_live_step_and_recent_changes_and_never_the_token(w):
    assert change(w, "dial.current", "sprint")[0] == 200
    state = call(w, "GET", "/api/state")[1]
    assert state["dial"]["current"] == "sprint" and state["dial"]["settings"] == ["thrift", "balanced", "sprint"]
    assert state["accounts"]["seats"]["verifier"] == "sol" and state["accounts"]["tracks"]["1"] == "default"
    assert state["live_step"] is False and state["balancing"] is False
    assert [(c["key"], c["old"], c["new"]) for c in state["changes"]] == [("dial.current", "auto", "sprint")]
    assert w.token not in json.dumps(state)


# ----------------------------------------------------------------------------------- the token lives off the repository

def test_a_new_token_is_long_random_and_readable_by_the_owner_alone(tmp_path):
    f = tmp_path / "a" / "b" / "token"
    t = panel.ensure_token(f)
    assert len(t) >= 32 and f.read_text().strip() == t
    assert stat.S_IMODE(f.stat().st_mode) == 0o600 and stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    assert panel.ensure_token(f) == t  # kept, not replaced
    assert panel.ensure_token(tmp_path / "c" / "token") != t


def test_a_token_is_refused_a_place_inside_the_repository(tmp_path):
    repo = Path(panel.REPO_ROOT)
    assert (repo / ".git").exists() or (repo / "OspreyFlow_Build").exists()
    for inside in (repo / "OspreyFlow_Build" / "token", BUILD / "tools" / "control_panel" / "token", repo / "token"):
        with pytest.raises(ValueError):
            panel.ensure_token(inside)
        assert not inside.exists()
    assert not panel.DEFAULT_TOKEN_FILE.resolve().is_relative_to(repo.resolve())
    assert not panel.DEFAULT_TOKEN_FILE.resolve().is_relative_to(panel.DEFAULT_DATA_DIR.resolve())


@pytest.mark.parametrize("content,mode", [("short", 0o600), ("", 0o600), ("x" * 40 + "\n", 0o644), ("x" * 40 + "\n", 0o640),
                                          ("x" * 40 + "\n", 0o604)])
def test_the_server_will_not_start_on_a_missing_short_or_readable_by_others_token(w, content, mode):
    f = w.cfg.token_file
    f.write_text(content)
    f.chmod(mode)
    with pytest.raises(ValueError):
        panel.make_server(w.cfg, port=0)
    f.unlink()
    with pytest.raises(ValueError):
        panel.make_server(w.cfg, port=0)


def test_a_token_is_compared_as_a_secret_not_as_text():
    assert panel.token_ok("Bearer abc", "abc") is True
    assert panel.token_ok("Bearer abd", "abc") is False
    assert panel.token_ok(None, "abc") is False
    assert panel.token_ok("Bearer abc", "") is False
    assert panel.token_ok("Bearer ", "") is False
