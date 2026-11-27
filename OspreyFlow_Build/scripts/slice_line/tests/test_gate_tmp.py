"""The gate's trees and environments live under the line's own folder, ~/.ospreyflow/slice-line/tmp/, never the
system's temporary folder (the owner's word of 27 November 2026, 65).

GR1e's merge gate, 27 November 2026, 03:35 UTC: at 76% of the line's suite every test began to fail,
"cannot import name 'BaseModel' from 'pydantic' (unknown location)" and "module 'yaml' has no attribute 'safe_load'".
macOS's dirhelper runs every day at 03:35 (/System/Library/LaunchDaemons/com.apple.bsd.dirhelper.plist) and deletes
the files older than three days (CLEAN_FILES_OLDER_THAN_DAYS) in the user's temporary folder, /var/folders/.../T. The
merge tree, its venv and node_modules were made there, and uv installs a venv by cloning its cache's files, which keep
the cache's dates (a merge tree made at 05:34 that morning had pydantic/__init__.py dated 17 October): the files went,
their new folders stayed, and the venv was emptied under the running gate.

So every tree and environment the gate and the dry run make (the before and merge trees, the envs and pytest bases,
the dry run's tree and venv) is under the line's own folder's tmp/, and each is removed when the run ends, as before.
In the test world the line's folder is the world's own, so nothing here reaches the real one.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from test_gates import built, merge, sh, verified, world  # noqa: F401  (world is a fixture)

SYSTEM_TMP = str(Path(tempfile.gettempdir()).resolve())


def made_paths(log: str, mark: str) -> list[str]:
    return sorted({p.rstrip(");,") for p in re.findall(r"(/\S*" + re.escape(mark) + r"\S*)", log)})


def own_system_tmp(w) -> Path:
    """The run's system temporary folder, its own (TMPDIR), so that what the gate leaves there is seen alone."""
    d = w["tmp"] / "system-tmp"
    d.mkdir(exist_ok=True)
    w["env"]["TMPDIR"] = str(d)
    return d


def under(path: str, root: Path) -> bool:
    return str(Path(path).resolve()).startswith(str(root.resolve()) + "/")


def test_the_merge_makes_its_trees_envs_and_bases_under_the_lines_tmp_and_removes_them(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    system = own_system_tmp(w)
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    done = json.loads((w["data"] / "records/S1/merged.json").read_text())
    log = (w["data"] / "records/S1" / done["gate_run"]).read_text()
    made = made_paths(log, "slice-S1-")
    assert any("-merge-" in m for m in made) and any("-before-" in m for m in made) and any("-envs-" in m for m in made), made
    tmp = w["data"] / "tmp"
    assert [m for m in made if not under(m, tmp)] == [], f"made outside {tmp}: {made}"
    assert [m for m in made if m.startswith(SYSTEM_TMP) and not under(m, w["tmp"])] == [], made
    assert sorted(p.name for p in system.glob("slice-*")) == [], "the merge made a tree or env in the system's tmp"
    assert [m for m in made if os.path.exists(m)] == [], "a tree or base was not removed"


def test_the_dry_run_makes_its_tree_and_venv_under_the_lines_tmp_and_removes_them(world):
    w = world
    log = w["tmp"] / "dry.log"
    system = own_system_tmp(w)
    seen = w["tmp"] / "made.txt"
    # every folder the dry run makes is seen as it is made (the venv's path is not in the log)
    code = (f"import sys, json, tempfile; sys.path.insert(0, {str(w['lines'])!r}); from pathlib import Path; "
            f"_m = tempfile.mkdtemp\n"
            f"def mk(*a, **k):\n    d = _m(*a, **k); open({str(seen)!r}, 'a').write(d + '\\n'); return d\n"
            f"tempfile.mkdtemp = mk\n"
            f"import common as c, dry_run; "
            f"print(json.dumps(dry_run.prove(c.slice_row('S1'), slot=None, log=Path({str(log)!r}))))")
    p = sh([w["py"], "-c", code], w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    made = sorted(set(made_paths(log.read_text(), "slice-dryrun")) |
                  {m for m in (seen.read_text().split() if seen.exists() else []) if "slice-dryrun" in m})
    assert any("-venv-" in m for m in made), made
    assert made, log.read_text()
    tmp = w["data"] / "tmp"
    assert [m for m in made if not under(m, tmp)] == [], f"made outside {tmp}: {made}"
    assert sorted(p.name for p in system.glob("slice-dryrun*")) == [], "the dry run made its tree or venv in the system's tmp"
    assert [m for m in made if os.path.exists(m)] == [], "the dry run's tree or venv was not removed"
    assert [p.name for p in tmp.iterdir()] == [] if tmp.exists() else True, "something left in the line's tmp"
