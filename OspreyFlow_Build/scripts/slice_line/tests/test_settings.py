"""The test settings a slice's frozen commands need, wherever they run (the owner's ruling 4(c); F4, F6, F8).

- F8: each slice gets a Playwright port slot of its own at slice_start (clear of scripts/lane_ports.tsv's lanes, of
  every unmerged slice's slot, of the stacks' and the owner's ports), set in the dry run, the Stop hook and the merge
  script's acceptance and checks runs. The stand-in for Playwright is lanePorts.ts's refusal: a linked worktree with
  no OSPREY_PORTS_SLOT is refused in words.
- F4: the merge script's acceptance and checks runs get an environment built as CI builds it (uv sync --frozen into a
  venv outside the tree, npm ci under CI's Node), and the tree has no node_modules or .venv when the full gate starts.
- F6: `env: full` makes slice_start.py build the worktree's environment itself, never lanes_launch.sh.
uv, npm and node are fakes that record what they were given, as the full gate's own tests use.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from test_dry_run import PLAYWRIGHT, row
from test_gates import built, merge, sh, started, stop_gate, verified, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
CI_YML = ('env:\n  UV_PYTHON: "3.12"\njobs:\n  a:\n    steps:\n      - uses: actions/setup-node@v4\n'
          '        with: { node-version: "22" }\n')


def fakes(w):
    """uv, npm and CI's node on PATH, recording each call (name, args, cwd, UV_PROJECT_ENVIRONMENT, slot)."""
    calls = w["tmp"] / "calls.tsv"
    b = w["tmp"] / "fakebin"
    b.mkdir(exist_ok=True)
    rec = (f'printf "%s\\t%s\\t%s\\t%s\\t%s\\n" "$(basename "$0")" "$*" "$PWD" "${{UV_PROJECT_ENVIRONMENT:-}}" '
           f'"${{OSPREY_PORTS_SLOT:-}}" >> "{calls}"\n')
    py = w["py"]
    scripts = {
        "uv": rec + 'if [ "$1" = sync ]; then v="${UV_PROJECT_ENVIRONMENT:-$PWD/.venv}"; mkdir -p "$v/bin"; '
                    f'printf \'#!/bin/sh\\nexec "{py}" "$@"\\n\' > "$v/bin/python"; chmod +x "$v/bin/python"; '
                    'echo "Python 3.12.9" > "$v/said"; fi\nexit 0\n',
        "npm": rec + '[ "$1" = ci ] && mkdir -p node_modules/.bin\nexit 0\n',
        "node": 'echo v22.1.0\n',
    }
    for name, body in scripts.items():
        (b / name).write_text("#!/bin/sh\n" + body)
        (b / name).chmod(0o755)
    w["env"]["PATH"] = f"{b}{os.pathsep}{w['env']['PATH']}"
    return calls


def ci_repo(w, lanes="merger\t13\nadmin\t16\n"):
    """The repository with what CI's environment is built from, a Playwright stand-in and the lanes' slots."""
    r = w["repo"]
    files = {"OspreyFlow_Core/pyproject.toml": "[project]\nname = 'x'\n", "OspreyFlow_Core/package-lock.json": "{}\n",
             ".github/workflows/ci.yml": CI_YML, "OspreyFlow_Build/scripts/lane_ports.tsv": "# lane\tslot\n" + lanes,
             "tools/keyboard.sh": PLAYWRIGHT, ".gitignore": "Claude outputs/\n.venv/\nnode_modules/\n"}
    for rel, text in files.items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(text)
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'build: ci settings' --trailer 'Slice-Records: yes'",
       r, w["env"])
    return fakes(w)


def calls_of(path):
    return [dict(zip(("name", "args", "cwd", "uv_env", "slot"), ln.split("\t")))
            for ln in (path.read_text().splitlines() if path.exists() else [])]


def slot_of(w, slice_id="S1"):
    return json.loads((w["data"] / f"records/{slice_id}/state.json").read_text()).get("slot")


# ------------------------------------------------------------------ F8: a slot of its own


def test_slice_start_gives_a_slice_a_slot_clear_of_the_lanes_and_every_unmerged_slice(world):
    w = world
    ci_repo(w)
    held = w["data"] / "records/S9"
    held.mkdir(parents=True)
    (held / "frozen.json").write_text(json.dumps({"slice": "S9", "checks": "export OSPREY_PORTS_SLOT=17 && true"}))
    (held / "state.json").write_text(json.dumps({"phase": "stopped", "slot": 18, "note": "x"}))
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    slot = slot_of(w)
    assert isinstance(slot, int) and slot >= 16 and slot not in (13, 16, 17, 18), slot


def test_the_dry_run_and_the_stop_hook_give_a_playwright_command_the_slices_slot(world):
    """AD2's commands carried no slot on 18 November: with the line's slot they run, at start and at Stop."""
    w = world
    ci_repo(w)
    row(w, checks="cd OspreyFlow_Core && sh ../tools/keyboard.sh")
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    (wt / "accept.sh").write_text("exit 0\n")
    sh("git add accept.sh && git commit -qm 'test: S1'", wt, w["env"])
    assert stop_gate(w, wt) is None
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    assert json.loads((w["data"] / f"records/S1/tests-{tip}.json").read_text())["green"]


def test_a_command_that_empties_the_slot_is_still_refused_at_start(world):
    w = world
    ci_repo(w)
    row(w, checks="cd OspreyFlow_Core && export OSPREY_PORTS_SLOT= && sh ../tools/keyboard.sh")
    p, _ = started(w)
    assert p.returncode != 0 and "OSPREY_PORTS_SLOT is not set" in p.stdout + p.stderr, p.stdout + p.stderr


# ------------------------------------------------------------------ F4: the merge script's runs


def test_the_merge_runs_acceptance_and_checks_with_a_ci_built_environment_outside_the_tree_and_the_slot(world):
    w = world
    calls = ci_repo(w)
    checks = ('sh tools/keyboard.sh && test -n "$VIRTUAL_ENV" && case "$VIRTUAL_ENV" in "$PWD"*) exit 7;; esac '
              '&& test -x "$VIRTUAL_ENV/bin/python" && test -d OspreyFlow_Core/node_modules')
    # These checks hold the merge's environment to CI's; the builder's Stop hook gives an env: none slice no venv, so
    # slice_start.py (B) refuses to start them as written. The slice starts on the first step and they reach it as the
    # owner's refreeze brings a row in: main's row and the frozen record changed together.
    row(w, checks="sh tools/keyboard.sh")
    wt, tip = built(w)
    tsv = w["repo"] / "OspreyFlow_Build/process/lanes/v062/slices.tsv"
    tsv.write_text(tsv.read_text().replace("\tsh tools/keyboard.sh\n", f"\t{checks}\n"))
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: S1 refrozen' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    fz = w["data"] / "records/S1/frozen.json"
    fz.write_text(json.dumps({**json.loads(fz.read_text()), "checks": checks}))
    verified(w, wt, tip)
    sees = w["tmp"] / "gate-sees.txt"
    w["env"]["TEST_GATE_SEES"] = str(sees)
    calls.unlink(missing_ok=True)
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    done = calls_of(calls)
    syncs = [c for c in done if c["name"] == "uv" and c["args"] == "sync --frozen"]
    assert len(syncs) == 2 and all(c["uv_env"] and not c["uv_env"].startswith(c["cwd"]) for c in syncs), syncs  # before, after
    assert [c["args"] for c in done if c["name"] == "npm"] == ["ci --no-audit --no-fund"] * 2
    assert sees.read_text().split() == ["clean"], sees.read_text()   # the full gate builds its own, fresh
    assert slot_of(w) and all(c["slot"] == str(slot_of(w)) for c in done), done


# ------------------------------------------------------------------ F6: env full


def test_env_full_builds_the_worktrees_environment_itself_never_the_lanes_launcher(world):
    w = world
    calls = ci_repo(w)
    launcher = w["repo"] / "OspreyFlow_Build/scripts/lanes_launch.sh"
    launcher.write_text(f"#!/bin/sh\necho called > {w['tmp']}/launcher-called\nexit 2\n")
    launcher.chmod(0o755)
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("S1\tCO1\tA test slice\t-\t1\t-\tnone", "S1\tCO1\tA test slice\t-\t1\t-\tfull"))
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: S1 env full' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert not (w["tmp"] / "launcher-called").exists()
    assert (wt / "OspreyFlow_Core/.venv/bin/python").is_file() and (wt / "OspreyFlow_Core/node_modules").is_dir()
    inside = [c for c in calls_of(calls) if c["cwd"] == str(wt / "OspreyFlow_Core")]
    assert [c["name"] for c in inside] == ["uv", "npm"], inside
    assert sh("git status --porcelain", wt).stdout.strip() == ""


def test_the_merge_runs_the_scans_of_the_touched_files_on_the_merge_result_and_sends_a_red_one_back(world):
    w = world
    ci_repo(w)
    from test_scans import SCANNER
    r = w["repo"]
    (r / "OspreyFlow_Build/pytest.ini").write_text("[pytest]\n")
    (r / "OspreyFlow_Build/tests").mkdir(parents=True, exist_ok=True)
    (r / "OspreyFlow_Build/tests/test_scan_demo.py").write_text(SCANNER)
    (r / "OspreyFlow_Core/apps").mkdir(parents=True, exist_ok=True)
    (r / "OspreyFlow_Core/apps/section.ts").write_text("export const x = 1;\n")
    (w["data"] / "bin/scan_map.tsv").write_text("tests/test_scan_demo.py\tOspreyFlow_Core/apps/\twalks the apps\n")
    shutil.copy(w["data"] / "bin/scan_map.tsv", w["lines"] / "scan_map.tsv")  # the merge script reads main's copy
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'test: a scanner' --trailer 'Slice-Records: yes'",
       r, w["env"])
    wt, tip = built(w, extra={"OspreyFlow_Core/apps/section.ts": "import forbidden from './x';\n"})
    verified(w, wt, tip)
    before = sh("git rev-parse main", r).stdout
    p = merge(w)
    assert p.returncode == 1 and "scan the files this slice touches are red" in p.stderr, p.stdout + p.stderr
    assert sh("git rev-parse main", r).stdout == before
    st = json.loads((w["data"] / "records/S1/state.json").read_text())
    rec = json.loads((w["data"] / f"records/S1/verify-gate-{tip}.json").read_text())
    assert st["phase"] == "refused" and "test_no_section_imports_the_forbidden_module" in json.dumps(rec["findings"])
