"""The owner's control panel (decisions D24-D26, 18 November 2026): what a slice can build of it.

A local server, on 127.0.0.1 only, that saves the owner's changes to the three yaml files the slice line's scripts read
(`dial.yaml`, `accounts.yaml`, `live_step.yaml`) and one stored setting, the switch for automatic balancing, which
nothing reads yet. It shows each account's windows and usage beside the accounts. It does not serve the dashboard:
the dashboard's controls, and the way the panel serves the dashboard folder, are the owner's own diffs.

Rules the code holds (each has a case in `tests/test_control_panel.py`, planted in the shape the server receives it,
and a second case that removes the check and shows the same request writing):

* It binds 127.0.0.1 and refuses to be given any other address (`make_server`).
* A request whose Host is not the panel's own (`127.0.0.1:<port>` or `localhost:<port>`) is refused 403, before
  anything else: a page on another site cannot reach it by pointing a name at 127.0.0.1 (`host_allowed`).
* A request without the panel's token, in `Authorization: Bearer <token>`, is refused 401 (`token_ok`). The token is in
  a file off the repository and off the slice line's data folder, readable by its owner only; the server will not start
  on one that is missing, short or readable by others (`load_token`). Nothing in a URL, a cookie or a body is a token.
* A value is checked before anything is written, against what the scripts accept, and a value the scripts would
  silently fall back from (an unknown `current`, a `live_step` that is not a plain true or false, an account name outside
  `[a-z][a-z0-9-]*`) is refused (`validate_value`). A file is edited one line at a time, so the owner's comments stay,
  and the result is read back with the same loader the scripts use before it is saved; the file is replaced whole or not
  at all.
* Every change is appended to `control-panel-changes.tsv` in the data folder (time, key, old value, new value), and a
  change that could not be logged is taken back. It is a file of its own, not `owner-changes.tsv`: the merge script
  trusts that one for the owner's acceptances, and a network door must not be able to write into it.

What this is not: "agents refused" is a second layer, not the refusal. An agent runs as the same macOS user and can run
any code, so the text-judging guard cannot stop it reaching a port or a file. The real refusal is the token: a secret
an agent has no reason to be given. The owner's guard rule (the panel's address and the token's path, refused to
agents) is a diff the owner applies.

Standard library, with PyYAML as the slice line's scripts use it (run it with OspreyFlow_Core's python).
"""
from __future__ import annotations

import argparse
import copy
import hmac
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
LANE_REL = "OspreyFlow_Build/process/lanes/v062"
LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 8765

DEFAULT_DATA_DIR = Path(os.environ.get("OSPREY_SLICE_HOME") or Path.home() / ".ospreyflow" / "slice-line")
DEFAULT_TOKEN_FILE = Path.home() / ".ospreyflow" / "control-panel" / "token"

CHANGES_LOG = "control-panel-changes.tsv"
CHANGES_HEADER = "at\tkey\told\tnew\n"
SETTINGS_FILE = "control-panel-settings.json"

#: The most a request body may be: the largest change is a key and a short value.
MAX_BODY = 4096
#: What the server reads and throws away of a refused oversize body, so the client sees the refusal, not a reset.
DRAIN_LIMIT = 1 << 20
TOKEN_MIN = 32
ACCOUNT_NAME = re.compile(r"[a-z][a-z0-9-]*")
ACCOUNT_NAME_MAX = 64
RECENT_CHANGES = 20
NO_FIGURE = "no figure"
WINDOWS = ("five_hour", "seven_day")
LOCK = threading.Lock()


class Refused(Exception):
    """A request the panel will not act on, and why. `status` is what the client is told."""

    def __init__(self, why: str, status: int = 400):
        super().__init__(why)
        self.why, self.status = why, status


@dataclass(frozen=True)
class Config:
    dial_file: Path
    accounts_file: Path
    live_step_file: Path
    data_dir: Path
    token_file: Path

    @classmethod
    def default(cls, lane_dir: Path | None = None, data_dir: Path | None = None, token_file: Path | None = None) -> "Config":
        lane = Path(lane_dir) if lane_dir else main_checkout() / LANE_REL
        return cls(lane / "dial.yaml", lane / "accounts.yaml", lane / "live_step.yaml",
                   Path(data_dir) if data_dir else DEFAULT_DATA_DIR, Path(token_file) if token_file else DEFAULT_TOKEN_FILE)


def main_checkout() -> Path:
    """The main checkout this tool belongs to (not a worktree), as the slice line's scripts find it."""
    p = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=str(REPO_ROOT),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise ValueError(f"the main checkout cannot be found: {p.stderr.strip()}")
    return Path(p.stdout.strip()).parent


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ------------------------------------------------------------------------------------------------------ the secret

def _off_the_repository(path: Path, forbidden: list[Path] | None) -> None:
    roots = list(forbidden) if forbidden is not None else [REPO_ROOT]
    if forbidden is None:
        try:
            roots.append(main_checkout())
        except (ValueError, OSError):
            pass
    target = Path(path).resolve()
    for root in roots:
        if target.is_relative_to(root.resolve()):
            raise ValueError(f"the token may not live inside the repository ({root}): {path}")


def load_token(path: Path) -> str:
    """The token in `path`, or ValueError: missing, not a file of this user's, readable by others, or short."""
    try:
        st = Path(path).stat()
        text = Path(path).read_text().strip()
    except OSError as e:
        raise ValueError(f"the token file {path} cannot be read: {e}")
    if not Path(path).is_file() or st.st_uid != os.getuid():
        raise ValueError(f"the token file {path} is not a file of this user's")
    if st.st_mode & 0o077:
        raise ValueError(f"the token file {path} is readable by others: chmod 600 it")
    if len(text) < TOKEN_MIN:
        raise ValueError(f"the token in {path} is shorter than {TOKEN_MIN} characters")
    return text


def ensure_token(path: Path, forbidden: list[Path] | None = None) -> str:
    """The token in `path`, made there (random, mode 600, in a folder of mode 700) if there is none. Refuses a path
    inside the repository. A file that is there but unusable is an error, never replaced: rotating is the owner's act."""
    path = Path(path)
    _off_the_repository(path, forbidden)
    if path.exists():
        return load_token(path)
    made = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if made:
        path.parent.chmod(0o700)
    token = secrets.token_urlsafe(32)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(token + "\n")
    return token


def host_allowed(host: str | None, port: int) -> bool:
    """Only the panel's own names, with its own port. No Host, no port, another name, another port: no."""
    return host is not None and host.lower() in (f"{LOOPBACK}:{port}", f"localhost:{port}")


def token_ok(authorization: str | None, token: str) -> bool:
    """`Authorization: Bearer <token>`, compared in constant time. An empty token never matches."""
    if not token or authorization is None or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(authorization[len("Bearer "):].encode("utf-8"), token.encode("utf-8"))


# ----------------------------------------------------------------------------------------------- reading the files

class Unreadable(Exception):
    pass


def _load_yaml(path: Path) -> dict:
    try:
        doc = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as e:
        raise Unreadable(f"{Path(path).name} cannot be read: {e}")
    if not isinstance(doc, dict):
        raise Unreadable(f"{Path(path).name} is not a mapping")
    return doc


def read_docs(cfg: Config) -> dict:
    return {"dial": _load_yaml(cfg.dial_file), "accounts": _load_yaml(cfg.accounts_file),
            "live_step": _load_yaml(cfg.live_step_file)}


def read_balancing(cfg: Config) -> bool:
    """On only when the file plainly says `{"balancing": true}`. Anything else, off."""
    try:
        data = json.loads((cfg.data_dir / SETTINGS_FILE).read_text())
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("balancing") is True


def _share(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value if 0 <= value <= 1 else None


def account_windows(cfg: Config, account: str) -> dict:
    """The account's two windows as its last session reported them. A figure that is not there, or is not a share between
    nought and one, says 'no figure': the key names are assumed from the stream, never guessed at."""
    try:
        doc = json.loads((cfg.data_dir / "accounts" / f"{account}.json").read_text())
    except (OSError, ValueError):
        doc = {}
    wins = doc.get("windows") if isinstance(doc, dict) else None
    wins = wins if isinstance(wins, dict) else {}
    out = {}
    for name in WINDOWS:
        entry = wins.get(name)
        share = _share(entry.get("utilization")) if isinstance(entry, dict) else None
        out[name] = {"utilisation": share, "text": NO_FIGURE if share is None else f"{round(share * 100)}%"}
    return out


def usage_totals(cfg: Config) -> dict[str, dict]:
    """Totals per account from usage.tsv, by column name. A row that is short, or has a figure that is not a whole
    number, is skipped whole."""
    try:
        lines = (cfg.data_dir / "usage.tsv").read_text().splitlines()
    except OSError:
        return {}
    if not lines:
        return {}
    head = lines[0].split("\t")
    cols = ("account", "input", "cache_create", "cache_read", "output")
    if any(c not in head for c in cols):
        return {}
    at = {c: head.index(c) for c in cols}
    totals: dict[str, dict] = {}
    for ln in lines[1:]:
        parts = ln.split("\t")
        if len(parts) < len(head):
            continue
        account = parts[at["account"]]
        nums = [parts[at[c]] for c in cols[1:]]
        if not ACCOUNT_NAME.fullmatch(account) or not all(re.fullmatch(r"[0-9]+", n) for n in nums):
            continue
        t = totals.setdefault(account, empty_totals())
        t["sessions"] += 1
        for c, n in zip(cols[1:], nums):
            t[c] += int(n)
    return totals


def empty_totals() -> dict:
    return {"sessions": 0, "input": 0, "cache_create": 0, "cache_read": 0, "output": 0}


def recent_changes(cfg: Config) -> list[dict]:
    try:
        lines = (cfg.data_dir / CHANGES_LOG).read_text().splitlines()[1:]
    except OSError:
        return []
    out = []
    for ln in lines[-RECENT_CHANGES:]:
        parts = ln.split("\t")
        try:
            out.append({"at": parts[0], "key": parts[1], "old": json.loads(parts[2]), "new": json.loads(parts[3])})
        except (IndexError, ValueError):
            continue
    return out


def _names(section: object) -> dict[str, object]:
    return {str(k): v for k, v in section.items()} if isinstance(section, dict) else {}


def state(cfg: Config) -> dict:
    docs = read_docs(cfg)
    dial, accounts = docs["dial"], docs["accounts"]
    seats, tracks = _names(accounts.get("seats")), _names(accounts.get("tracks"))
    named = {v for v in (*seats.values(), *tracks.values()) if isinstance(v, str) and ACCOUNT_NAME.fullmatch(v)}
    totals = usage_totals(cfg)
    names = sorted(named | set(totals))
    live = docs["live_step"].get("live_step")
    return {
        "dial": {"current": dial.get("current"), "day": dial.get("day"), "night": dial.get("night"),
                 "settings": list(_names(dial.get("settings")))},
        "accounts": {"seats": seats, "tracks": tracks},
        "usage": {a: {"windows": account_windows(cfg, a), "totals": totals.get(a, empty_totals())} for a in names},
        "live_step": live if isinstance(live, bool) else None,
        "balancing": read_balancing(cfg),
        "changes": recent_changes(cfg),
    }


# ------------------------------------------------------------------------------------------------ checking a change

def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


def _account_name(value: object) -> str:
    if not isinstance(value, str) or len(value) > ACCOUNT_NAME_MAX or not ACCOUNT_NAME.fullmatch(value):
        raise Refused("an account name is lower-case letters, digits and hyphens, starting with a letter")
    return value


def validate_value(key: object, value: object, docs: dict) -> object:
    """The value to write for `key`, or Refused. Stricter than the scripts on purpose: where they fall back silently, the
    panel refuses."""
    if not isinstance(key, str):
        raise Refused("the key must be text")
    parts = key.split(".")
    settings = list(_names(docs["dial"].get("settings")))
    if key == "dial.current":
        if not isinstance(value, str) or value not in ["auto", *settings]:
            raise Refused(f"current is auto or one of: {', '.join(settings)}")
        return value
    if key in ("dial.day", "dial.night"):
        if not isinstance(value, str) or value not in settings:
            raise Refused(f"{parts[1]} is one of: {', '.join(settings)}")
        return value
    if len(parts) == 3 and parts[:2] in (["accounts", "seats"], ["accounts", "tracks"]):
        section = _names(docs["accounts"].get(parts[1]))
        if parts[2] not in section:
            raise Refused(f"{parts[2]!r} is not in the {parts[1]} the accounts file names")
        return _account_name(value)
    if key in ("live_step", "balancing"):
        if not _is_bool(value):
            raise Refused(f"{key} is true or false, as a JSON boolean")
        return value
    raise Refused("that is not something the panel changes")


def current_value(cfg: Config, docs: dict, key: str) -> object:
    parts = key.split(".")
    if key == "balancing":
        return read_balancing(cfg)
    if key == "live_step":
        return docs["live_step"].get("live_step")
    if parts[0] == "dial":
        return docs["dial"].get(parts[1])
    return _names(docs["accounts"].get(parts[1])).get(parts[2])


# ----------------------------------------------------------------------------------------------- writing a change

_PLAIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _emit(value: object) -> str:
    """The value as text for a yaml line: bare where it reads back as the same string, quoted where it would not (no,
    on, null, true read back as something else bare)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if not isinstance(value, str):
        raise ValueError(f"cannot write {value!r}")
    if _PLAIN.fullmatch(value):
        try:
            if yaml.safe_load(value) == value:
                return value
        except yaml.YAMLError:
            pass
    return json.dumps(value)


def _line_pattern(key: str, indented: bool) -> re.Pattern:
    k = re.escape(key)
    lead = r"[ \t]+" if indented else r""
    return re.compile(rf"^(?P<head>{lead}(?:\"{k}\"|'{k}'|{k}):[ \t]*)(?P<val>\"[^\"\n]*\"|'[^'\n]*'|[^\s#\"'][^\s#]*)"
                      rf"(?P<rest>[ \t]*(?:#.*)?)$")


def edit_text(text: str, path: tuple[str, ...], value: object) -> str:
    """`text` with the one line at `path` (a top-level key, or a key under a top-level section) given `value`, and every
    other byte as it was. ValueError when the file's shape is not one line for that key."""
    lines = text.splitlines(keepends=True)
    lo, hi = 0, len(lines)
    if len(path) == 2:
        head = re.compile(rf"^{re.escape(path[0])}:[ \t]*(?:#.*)?$")
        starts = [i for i, ln in enumerate(lines) if head.match(ln.rstrip("\r\n"))]
        if len(starts) != 1:
            raise ValueError(f"the file has {len(starts)} sections named {path[0]!r}, not one")
        lo = starts[0] + 1
        hi = lo
        while hi < len(lines) and (not lines[hi].strip() or lines[hi].lstrip().startswith("#") or lines[hi][0] in " \t"):
            hi += 1
    pat = _line_pattern(path[-1], indented=len(path) == 2)
    hits = [(i, pat.match(lines[i].rstrip("\r\n"))) for i in range(lo, hi)]
    hits = [(i, m) for i, m in hits if m]
    if len(hits) != 1:
        raise ValueError(f"the file has {len(hits)} lines for {'.'.join(path)}, not one")
    i, m = hits[0]
    eol = lines[i][len(lines[i].rstrip("\r\n")):]
    lines[i] = m.group("head") + _emit(value) + m.group("rest") + eol
    return "".join(lines)


def _set_path(doc: dict, path: tuple[str, ...], value: object) -> dict:
    out = copy.deepcopy(doc)
    node = out
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = value
    return out


def _leaf(doc: object, path: tuple[str, ...]) -> object:
    for p in path:
        doc = doc.get(p) if isinstance(doc, dict) else None
    return doc


def reads_back(got: object, doc: dict, path: tuple[str, ...], value: object) -> bool:
    """The edited file, as the scripts' loader reads it (`got`), is `doc` with `value` at `path` and nothing else different,
    and `value` is still the type it was given (`True` is not `1`). The guard against a line edit that a file's shape
    (a block scalar, a continuation line) makes read as something else."""
    return got == _set_path(doc, path, value) and type(_leaf(got, path)) is type(value)


def _file_and_path(cfg: Config, key: str) -> tuple[Path, str, tuple[str, ...]]:
    parts = key.split(".")
    if parts[0] == "dial":
        return cfg.dial_file, "dial", (parts[1],)
    if parts[0] == "accounts":
        return cfg.accounts_file, "accounts", (parts[1], parts[2])
    return cfg.live_step_file, "live_step", ("live_step",)


def _replace(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".panel-tmp")
    tmp.write_bytes(data)
    if path.exists():
        shutil.copymode(path, tmp)
    os.replace(tmp, path)


def _log(cfg: Config, key: str, old: object, new: object) -> None:
    log = cfg.data_dir / CHANGES_LOG
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    fresh = not log.exists()
    with log.open("a") as fh:
        if fresh:
            fh.write(CHANGES_HEADER)
        fh.write("\t".join([now(), key, json.dumps(old), json.dumps(new)]) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def apply_change(cfg: Config, key: object, value: object) -> dict:
    """Check, write, log: or refuse and leave every file as it was."""
    with LOCK:
        try:
            docs = read_docs(cfg)
        except Unreadable as e:
            raise Refused(str(e), 500)
        value = validate_value(key, value, docs)
        old = current_value(cfg, docs, key)
        if old == value and type(old) is type(value):
            return {"ok": True, "key": key, "old": old, "new": value, "changed": False}
        if key == "balancing":
            target = cfg.data_dir / SETTINGS_FILE
            new_bytes = json.dumps({"balancing": value}).encode()
        else:
            target, which, path = _file_and_path(cfg, key)
            try:
                new_text = edit_text(target.read_text(), path, value)
                got = yaml.safe_load(new_text)
            except (ValueError, OSError, yaml.YAMLError) as e:
                raise Refused(f"the panel cannot edit {target.name} safely: {e}", 500)
            if not reads_back(got, docs[which], path, value):
                raise Refused(f"the panel could not write that to {target.name} so that it reads back the same", 500)
            new_bytes = new_text.encode()
        original = target.read_bytes() if target.exists() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        _replace(target, new_bytes)
        try:
            _log(cfg, key, old, value)
        except OSError as e:
            if original is None:
                target.unlink(missing_ok=True)
            else:
                _replace(target, original)
            raise Refused(f"the change could not be logged, so it was not made: {e}", 500)
        return {"ok": True, "key": key, "old": old, "new": value, "changed": True}


# --------------------------------------------------------------------------------------------------------- serving

def _strict_object(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"{k!r} twice")
        out[k] = v
    return out


def _refuse_constant(name: str) -> None:
    raise ValueError(f"{name} is not JSON")


def parse_change(body: bytes) -> tuple[object, object]:
    try:
        doc = json.loads(body.decode("utf-8"), object_pairs_hook=_strict_object, parse_constant=_refuse_constant)
    except (ValueError, UnicodeDecodeError) as e:
        raise Refused(f"the body is not one JSON object: {e}")
    if not isinstance(doc, dict) or set(doc) != {"key", "value"}:
        raise Refused('the body is exactly {"key": ..., "value": ...}')
    return doc["key"], doc["value"]


class Handler(BaseHTTPRequestHandler):
    server_version = "OspreyControlPanel"
    sys_version = ""

    def log_message(self, *args) -> None:  # the access log would carry what a client put in an address
        pass

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _refuse(self, status: int, why: str) -> None:
        self._send(status, {"ok": False, "refused": why})

    def _read_body(self) -> bytes:
        raw = self.headers.get("Content-Length")
        if raw is None or not re.fullmatch(r"[0-9]{1,9}", raw):
            raise Refused("a Content-Length is needed", 411)
        length = int(raw)
        if length > MAX_BODY:
            left = min(length, DRAIN_LIMIT)
            while left > 0:
                chunk = self.rfile.read(min(left, 65536))
                if not chunk:
                    break
                left -= len(chunk)
            raise Refused(f"the body is over {MAX_BODY} bytes", 413)
        return self.rfile.read(length)

    def _handle(self) -> None:
        cfg: Config = self.server.cfg  # type: ignore[attr-defined]
        port = self.server.server_address[1]
        if not host_allowed(self.headers.get("Host"), port):
            return self._refuse(403, "this is not the panel's own address")
        if not token_ok(self.headers.get("Authorization"), self.server.token):  # type: ignore[attr-defined]
            return self._refuse(401, "a token is needed")
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/state":
                if self.command != "GET":
                    return self._refuse(405, "GET only")
                return self._send(200, state(cfg))
            if path == "/api/change":
                if self.command != "POST":
                    return self._refuse(405, "POST only")
                key, value = parse_change(self._read_body())
                return self._send(200, apply_change(cfg, key, value))
            return self._refuse(404, "no such page")
        except Refused as e:
            return self._refuse(e.status, e.why)
        except Unreadable as e:
            return self._refuse(500, str(e))

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _handle


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, cfg: Config, token: str):
        self.cfg, self.token = cfg, token
        super().__init__(address, Handler)

    def serve_forever(self, poll_interval: float = 0.05) -> None:  # a stop is heard in a twentieth of a second
        super().serve_forever(poll_interval)


def make_server(cfg: Config, host: str = LOOPBACK, port: int = DEFAULT_PORT) -> PanelServer:
    """A server on 127.0.0.1, with the token read from its file. ValueError, before any socket is opened, for any other
    address or an unusable token."""
    if host != LOOPBACK:
        raise ValueError(f"the panel is bound to {LOOPBACK} only, not {host!r}")
    token = load_token(cfg.token_file)
    return PanelServer((host, port), cfg, token)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.control_panel", description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", default=LOOPBACK, help=f"only {LOOPBACK} is accepted")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--lane-dir", help="the folder with dial.yaml, accounts.yaml and live_step.yaml (default: the main checkout's)")
    ap.add_argument("--data-dir", help=f"the slice line's data folder (default: {DEFAULT_DATA_DIR})")
    ap.add_argument("--token-file", help=f"(default: {DEFAULT_TOKEN_FILE}; made if there is none)")
    args = ap.parse_args(argv)
    if args.host != LOOPBACK:
        print(f"refused: the panel is bound to {LOOPBACK} only, not {args.host!r}", file=sys.stderr)
        return 2
    try:
        cfg = Config.default(args.lane_dir, args.data_dir, args.token_file)
        ensure_token(cfg.token_file)
        server = make_server(cfg, args.host, args.port)
    except (ValueError, OSError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print(f"The control panel is on http://{LOOPBACK}:{server.server_address[1]}/ . The token is in {cfg.token_file}"
          " (not printed); send it as 'Authorization: Bearer <token>'.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
