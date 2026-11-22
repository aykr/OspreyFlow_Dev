"""The named lists the early-warning runner works from, and their derivation from the repository.

The owner's rulings 1 and 3 (DEMO_SERVER_EARLY_WARNING_BRIEF.md, 21 November 2026):

* `lists.tsv`: every `make -k ci` target (OspreyFlow_Build's `ci:` and, for `core-check`, OspreyFlow_Core's
  `check:`) and every test file that starts a container or binds a fixed port, each `run` or `not-run`, with the
  reason and the evidence (file and line). On the demo server the runner runs only what starts no container and binds
  no fixed port; the rest is reported "not run". A test that starts a container but runs under the repository's own
  docker guard (tests/local_docker_guard.py: with `no-local-stacks` present every docker call skips, in words) is
  `run`, reason `container-guarded`: its docker calls are skipped and named "not run" by the runner, the rest of the
  file runs.
* `mac_only.tsv`: every test whose snapshot files exist only for another platform (`*-darwin.png` with no
  `*-linux.png`), with the snapshot files as evidence. Reported "not run on this machine", never red.

`derive_*` re-derive both from a tree; `check()` says what a list misses or holds stale. A test row whose note begins
`pending: <slice>` may name a file the tree does not have yet (a row written ahead of the slice that adds it); once
the file is there it is checked as any other row. A candidate the list does
not name is never run by the runner: it is reported "not run (unlisted)", so a new one cannot slip in.

Standard library only (the server runs it under its own python3). `python3 lists.py <tree>` prints check()'s findings.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LISTS = HERE / "lists.tsv"
MAC_ONLY = HERE / "mac_only.tsv"
COLUMNS = ("kind", "name", "verdict", "reason", "evidence", "note")
KINDS = ("ci", "core", "test")
VERDICTS = ("run", "not-run")
REASONS = ("-", "split", "container", "container-guarded", "fixed-port", "client-names", "no-tool")

BUILD_MAKEFILE = "OspreyFlow_Build/Makefile"
CORE_MAKEFILE = "OspreyFlow_Core/Makefile"

#: A line that starts a container: the docker CLI as a program (argv or shell), compose up, testcontainers.
CONTAINER = re.compile(
    r"testcontainers|DockerContainer|\[\s*[\"']docker[\"']|[\"']docker[\"']\s*,|"
    r"\bdocker\s+(?:run|compose|build|exec|create|start|pull|network|volume)\b|[\"']compose[\"']\s*,\s*[\"']up[\"']")
#: A server call or a port flag with a literal port other than 0 (a fixed port). Port 0 asks the system for a free one.
SERVER_CALL = re.compile(r"\.bind\(|HTTPServer\(|TCPServer\(|start_server\(|create_server\(|uvicorn\.run\(|\.listen\(")
LITERAL_PORT = re.compile(r"(?<![\w.])([1-9]\d{1,4})(?![\w.])")
PORT_FLAG = re.compile(r"--port[\"']?\s*[,= ]\s*[\"']?([1-9]\d{1,4})\b")
PY_TESTS = ("OspreyFlow_Build/tests",)
JS_TEST = re.compile(r"\.(?:test|spec)\.(?:ts|tsx|mjs|js)$")
JS_ROOTS = ("OspreyFlow_Build/tests", "OspreyFlow_Core/apps", "OspreyFlow_Core/packages")
SKIP_DIRS = {"node_modules", ".venv", "dist", "__pycache__", ".git"}


def read_tsv(path: Path, columns=COLUMNS) -> list[dict]:
    rows = []
    for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if parts[0] == columns[0]:
            continue
        parts += [""] * (len(columns) - len(parts))
        row = dict(zip(columns, (p.strip() for p in parts)))
        row["_line"] = n
        rows.append(row)
    return rows


# ----------------------------------------------------------------------------------------------- make targets

def _defs(text: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r"^([A-Z_]+)\s*[:?]?=\s*(.*)$", text, re.M):
        out.setdefault(m.group(1), m.group(2))
    return out


def prerequisites(text: str, target: str) -> list[str]:
    m = re.search(r"^%s:([^=\n]*)$" % re.escape(target), text, re.M)
    return m.group(1).split() if m else []


def recipe(text: str, target: str) -> list[tuple[int, str]]:
    """The target's recipe lines, numbered, with this Makefile's own simple variables expanded once."""
    lines = text.splitlines()
    defs = _defs(text)
    out = []
    for i, ln in enumerate(lines):
        if re.match(r"^%s:(?!=)" % re.escape(target), ln):
            for j in range(i + 1, len(lines)):
                if not lines[j].startswith("\t"):
                    break
                body = re.sub(r"\$\(([A-Z_]+)\)", lambda v: defs.get(v.group(1), v.group(0)), lines[j])
                out.append((j + 1, body))
            break
    return out


def _npm_script(tree: Path, body: str) -> tuple[str, str] | None:
    m = re.search(r"npm run ([\w:-]+) --workspace ([\w/.-]+)", body)
    if not m:
        return None
    pkg = tree / "OspreyFlow_Core" / m.group(2) / "package.json"
    try:
        script = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {}).get(m.group(1), "")
    except (OSError, ValueError):
        return None
    return str(pkg.relative_to(tree)), script


def target_evidence(tree: Path, makefile: str, target: str) -> list[tuple[str, str]]:
    """Why a target cannot run on the shared daemon: (reason, file:line) for each container or fixed-port step."""
    text = (tree / makefile).read_text(encoding="utf-8")
    found = []
    for n, body in recipe(text, target):
        if re.search(r"(?:^|[\s;&|(])docker\s", body):
            found.append(("container", "%s:%d" % (makefile, n)))
        npm = _npm_script(tree, body)
        if npm and "playwright test" in npm[1]:
            cfg = re.search(r"--config ([\w/.-]+)", npm[1])
            where = "%s (%s)" % (npm[0], npm[1])
            if cfg:
                ws = Path(npm[0]).parent
                conf = tree / ws / cfg.group(1)
                if conf.is_file():
                    for k, ln in enumerate(conf.read_text(encoding="utf-8").splitlines(), 1):
                        if "webServer" in ln:
                            where = "%s:%d" % (conf.relative_to(tree), k)
                            break
            found.append(("fixed-port", where))
        m = re.search(r"-m (tools\.[\w.]+)", body)
        if m:
            tool = tree / "OspreyFlow_Build" / (m.group(1).replace(".", "/") + ".py")
            for dep in [tool] + _imported_tools(tree, tool):
                if dep.is_file():
                    for k, ln in enumerate(dep.read_text(encoding="utf-8").splitlines(), 1):
                        if CONTAINER.search(ln) and not ln.lstrip().startswith("#"):
                            found.append(("container", "%s:%d" % (dep.relative_to(tree), k)))
    return found


def _imported_tools(tree: Path, tool: Path) -> list[Path]:
    try:
        text = tool.read_text(encoding="utf-8")
    except OSError:
        return []
    return [tree / "OspreyFlow_Build" / (m.group(1).replace(".", "/") + ".py")
            for m in re.finditer(r"^from (tools\.[\w.]+) import", text, re.M)]


def derive_targets(tree: Path) -> list[dict]:
    """Every target `make -k ci` runs, with its derived evidence. core-check is split into Core's check targets."""
    out = []
    build = (tree / BUILD_MAKEFILE).read_text(encoding="utf-8")
    core = (tree / CORE_MAKEFILE).read_text(encoding="utf-8")
    for t in prerequisites(build, "ci"):
        out.append({"kind": "ci", "name": t, "found": [] if t == "core-check" else target_evidence(tree, BUILD_MAKEFILE, t)})
    for t in prerequisites(core, "check"):
        out.append({"kind": "core", "name": t, "found": target_evidence(tree, CORE_MAKEFILE, t)})
    return out


# ----------------------------------------------------------------------------------------------- test files

def _files(tree: Path, roots, want) -> list[Path]:
    out = []
    for r in roots:
        base = tree / r
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and not (SKIP_DIRS & set(p.relative_to(tree).parts)) and want(p):
                out.append(p)
    return out


def file_evidence(path: Path, tree: Path) -> list[tuple[str, str]]:
    rel = str(path.relative_to(tree))
    found = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return found
    for n, ln in enumerate(lines, 1):
        code = ln.strip()
        if code.startswith(("#", "//", "*")):
            continue
        if CONTAINER.search(ln):
            found.append(("container", "%s:%d" % (rel, n)))
        if SERVER_CALL.search(ln) and LITERAL_PORT.search(ln.split(SERVER_CALL.search(ln).group(0), 1)[1]):
            found.append(("fixed-port", "%s:%d" % (rel, n)))
        elif PORT_FLAG.search(ln):
            found.append(("fixed-port", "%s:%d" % (rel, n)))
    return found


def derive_tests(tree: Path) -> dict[str, list[tuple[str, str]]]:
    """Every test file (and test helper) that starts a container or binds a fixed port, with its evidence."""
    out = {}
    for p in _files(tree, PY_TESTS, lambda p: p.suffix == ".py") + _files(tree, JS_ROOTS, lambda p: bool(JS_TEST.search(p.name))):
        ev = file_evidence(p, tree)
        if ev:
            out[str(p.relative_to(tree))] = ev
    return out


# ----------------------------------------------------------------------------------------------- Mac-only snapshots

PLATFORM_PNG = re.compile(r"-(darwin|linux|win32)\.png$")


def derive_mac_only(tree: Path) -> dict[str, list[str]]:
    """Each test whose snapshots carry another platform's name and none for Linux: spec file -> its snapshot files."""
    out: dict[str, list[str]] = {}
    for d in _files(tree, ("OspreyFlow_Core", "OspreyFlow_Build"), lambda p: bool(PLATFORM_PNG.search(p.name))):
        folder = d.parent
        if not folder.name.endswith("-snapshots"):
            continue
        spec = folder.parent / folder.name[: -len("-snapshots")]
        out.setdefault(str(spec.relative_to(tree)), []).append(str(d.relative_to(tree)))
    for spec, files in list(out.items()):
        if any(f.endswith("-linux.png") for f in files):
            del out[spec]  # it has Linux snapshots: it runs on Linux like anywhere else
        else:
            out[spec] = sorted(files)
    return out


# ----------------------------------------------------------------------------------------------- the check

def check(tree: Path, lists: Path = LISTS, mac_only: Path = MAC_ONLY) -> list[str]:
    """What the named lists miss or hold stale against `tree`: [] when they match it."""
    problems = []
    rows = read_tsv(lists)
    seen: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["kind"], r["name"])
        if r["kind"] not in KINDS or r["verdict"] not in VERDICTS or r["reason"] not in REASONS:
            problems.append("lists.tsv line %d: kind, verdict or reason is not one the runner knows" % r["_line"])
        if key in seen:
            problems.append("lists.tsv names %s %s twice" % key)
        seen[key] = r
        if r["verdict"] == "not-run" and not r["evidence"]:
            problems.append("lists.tsv: %s %s is not run but gives no evidence" % key)
    targets = derive_targets(tree)
    names = {(t["kind"], t["name"]) for t in targets}
    for t in targets:
        r = seen.get((t["kind"], t["name"]))
        if r is None:
            problems.append("make target %s (%s) is in neither list" % (t["name"], t["kind"]))
            continue
        if r["verdict"] == "run" and t["found"] and r["reason"] != "split" and not r["note"]:
            problems.append("make target %s is listed run but %s at %s, with no note saying why it may run"
                            % (t["name"], t["found"][0][0], t["found"][0][1]))
    tests = derive_tests(tree)
    for path, ev in tests.items():
        r = seen.get(("test", path))
        if r is None:
            problems.append("test file %s %s (%s) and is in neither list" % (
                path, "starts a container" if ev[0][0] == "container" else "binds a fixed port", ev[0][1]))
            continue
        kinds = {k for k, _ in ev}
        if r["verdict"] == "run" and "fixed-port" in kinds and not r["note"]:
            problems.append("test file %s binds a fixed port (%s) and is listed run with no note saying why it may"
                            % (path, next(w for k, w in ev if k == "fixed-port")))
        if r["verdict"] == "run" and kinds == {"container"} and r["reason"] != "container-guarded":
            problems.append("test file %s starts a container and is listed run without reason container-guarded" % path)
    for (kind, name), r in seen.items():
        if kind == "test" and name not in tests:
            if not (tree / name).exists() and r["note"].startswith("pending: "):
                continue  # a row written ahead of the slice that adds the file (004): stale once the file is there
            problems.append("lists.tsv names %s, which no longer starts a container or binds a fixed port (stale)" % name)
        if kind in ("ci", "core") and (kind, name) not in names:
            problems.append("lists.tsv names make target %s (%s), which make -k ci no longer runs (stale)" % (name, kind))
    mac = {r["name"]: r for r in read_tsv(mac_only, ("name", "snapshots", "evidence"))}
    derived = derive_mac_only(tree)
    for spec, files in derived.items():
        if spec not in mac:
            problems.append("test %s has snapshots only for another platform (%s) and is not in mac_only.tsv"
                            % (spec, files[0]))
    for spec in mac:
        if spec not in derived:
            problems.append("mac_only.tsv names %s, whose snapshots are no longer platform-only (stale)" % spec)
    return problems


def not_run_tests(tree: Path, lists: Path = LISTS) -> tuple[list[dict], list[str]]:
    """The test files the runner leaves out: those listed not-run, and every candidate the list does not name."""
    rows = {r["name"]: r for r in read_tsv(lists) if r["kind"] == "test"}
    listed = [r for r in rows.values() if r["verdict"] == "not-run"]
    unlisted = sorted(p for p in derive_tests(tree) if p not in rows)
    return listed, unlisted


if __name__ == "__main__":
    tree = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parents[3])
    found = check(tree)
    print("\n".join(found) or "the lists match the repository")
    sys.exit(1 if found else 0)
