"""v052-r1upgrade's plants (rule 15): each a real mutation of the code under test at its own call
site, run against the one test meant to catch it, with a fresh PYTHONPYCACHEPREFIX each time; the
file is restored after every plant. Run from OspreyFlow_Build: python process/lanes/platform/v052-r1upgrade/plants.py
"""

# ruff: noqa: E501 - a record's driver: each plant's old and new text on its own line, as read.
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

R1 = Path("process/lanes/platform/gates/r1_kind.py")
S3 = Path("tests/fixtures/cloud_platform/s3_standin.py")
UP, DE = "tests/test_r1_kind_upgrade.py", "tests/test_r1_kind_decommission.py"

PLANTS = [
    ("the install puts the kept render back and renders only without an INSTALL.md (main's)", R1,
     '    if name == "INSTALL":\n        install_render()\n    else:\n        render_back()\n',
     '    render_back()\n    if name == "INSTALL" and not (FOLDER / "INSTALL.md").exists():\n'
     '        sh(".venv/bin/python", "-m", "harness.render", "--config", str(CONFIG), "--allow-unpinned")\n',
     UP, "upgrade_runs"),
    ("any kept render put back over the candidate's", R1,
     "    if _release_files(KEPT) == _release_files(FOLDER):\n", "    if True:\n", UP, "upgrade_runs"),
    ("a resumed install's kept render never put back", R1,
     "    if _release_files(KEPT) == _release_files(FOLDER):\n", "    if False:\n", UP, "resumed"),
    ("destroy leaves the sets in the backups bucket", R1,
     '            "shutil.rmtree(p)\\n"\n            "print(n)")', '            "print(n)")', DE, "destroy_removes"),
    ("destroy leaves the key usable", R1,
     '                key["state"] = "PendingDeletion"\n', "", DE, "destroy_removes"),
    ("destroy run twice goes ahead", R1,
     '        if not any(b["name"] == backups for b in config["buckets"]):\n',
     '        if False:\n', DE, "aws_refuses and NoSuchBucket"),
    ("destroy over a key already pending deletion goes ahead", R1,
     '        if keys[0].get("state") == "PendingDeletion":\n', '        if False:\n', DE, "aws_refuses and KMSInvalidStateException"),
    ("the Terraform's removal takes the platform's own buckets too", R1,
     "p.is_dir() and p.name.startswith({prefix!r})", "p.is_dir() and True", DE, "destroy_removes"),
    ("keep drops the backups bucket from the stand-in", R1,
     '        config["buckets"] = [b for b in config["buckets"] if b["name"] == backups]\n',
     '        config["buckets"] = []\n', DE, "keep_leaves"),
    ("R1's keep given though the run asked for no choice", R1,
     '    if os.environ.get("R1_BACKUPS") == "unset":\n', '    if False:\n', DE, "no_choice"),
    ("the S3 stand-in serves a key pending deletion", S3,
     "        if key_arn in self.pending_deletion:\n", "        if False:\n",
     "tests/cloud_platform_backup/test_s3_standin.py", "pending_deletion"),
]


def main() -> int:
    env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
           "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
    env.pop("OSPREY_LANE", None)
    failures = 0
    for n, (what, path, old, new, test, k) in enumerate(PLANTS, 1):
        text = path.read_text()
        assert text.count(old) == 1, f"plant {n} does not apply: {what}"
        path.write_text(text.replace(old, new))
        try:
            env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp(prefix="pyc-")
            done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test, "-k", k],
                                  capture_output=True, text=True, env=env, check=False)
        finally:
            path.write_text(text)
        last = done.stdout.strip().splitlines()[-1]
        red = done.returncode != 0 and "failed" in last
        failures += not red
        print(f"plant {n}: {what}\n  {test} -k {k!r}: {'RED' if red else 'NOT RED'} ({last})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
