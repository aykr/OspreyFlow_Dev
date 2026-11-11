"""`harness.render.write_private` never leaves `deployment.env` half-written (CARRIES, the
orchestrator's review of the upgrade fix, 10 November 2026): it wrote in place (`O_TRUNC`), so a
full disk or a crash mid-write left the deployment's every secret truncated, with no restore. Now a
`600` file beside it is written, flushed to disk, given the old file's owner, and renamed over it.
`deployment.env` is read as an `env_file` when a container is made, never mounted, so its new inode
is what the next container reads.
- `test_it_is_600_from_the_start_and_leaves_nothing_beside_it`

A failure part way, the old owner under sudo (given an owner the runner is not, which the first
version of this file could not tell from the runner's own) and a symlinked file are proved for every
writer of `deployment.env` at once, in `test_atomic_writes.py` (`harness.atomic.replace_whole`).
"""

from __future__ import annotations

from pathlib import Path

from harness.render import write_private

OLD = "OSPREY_POSTGRES_PASSWORD=held-for-years\nOSPREY_KEYCLOAK_ADMIN_PASSWORD=also-held\n"


def test_it_is_600_from_the_start_and_leaves_nothing_beside_it(tmp_path: Path) -> None:
    env = tmp_path / "deployment.env"
    env.write_text(OLD, encoding="utf-8")
    env.chmod(0o644)
    write_private(env, "X=1\n")
    assert env.read_text(encoding="utf-8") == "X=1\n"
    assert env.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["deployment.env"]
    write_private(tmp_path / "new.env", "Y=2\n")  # a file not there before
    assert (tmp_path / "new.env").stat().st_mode & 0o777 == 0o600
