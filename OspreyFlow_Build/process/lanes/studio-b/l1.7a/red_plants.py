"""L1.7a's red-then-green record (rules 12 and 15): each plant is one exact edit to the code under
test; the script applies it, runs the named test files, restores the file byte for byte and writes
what ran to `red-<n>-<slug>.txt` beside it, headed by the commit, the plant and the command.

Run from OspreyFlow_Core with the closed offline ports pinned (no stack):
    .venv/bin/python ../OspreyFlow_Build/process/lanes/studio-b/l1.7a/red_plants.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[4] / "OspreyFlow_Core"
PUBLISH = CORE / "services/api/studio_publish.py"
REPO_TESTS = "../OspreyFlow_Build/tests/services/api/test_recipe_repository.py"
COMMIT_TESTS = "../OspreyFlow_Build/tests/services/api/test_studio_publish_commit_file.py"
IMAGE_TESTS = "../OspreyFlow_Build/tests/test_connectors_are_carried_into_the_image.py"

INDEX_BLOCK = """    repo.object_store.add_object(blob)
    index = repo.open_index(config=ConfigFile())  # its settings from no config, not the user's
    index[path] = index_entry_from_stat(written, blob.id)
    index.write()
"""
AFTER_REF = """                "committed; publish again"
            )
"""
CAS_CLOSE = """        ):  # fmt: skip
            raise GitCommitError(
                f"the recipe repository's HEAD moved"""
ID_CASES = [f"test_a_recipe_id_that_is_not_one_file_name_is_refused[{case}]"
            for case in ("../x", ".git/x", "../../outside", "a/b", "..", ".hidden", "")]  # fmt: skip
RACE = "test_a_real_writer_moving_head_mid_commit_is_refused"
FAKE_REFUSAL = "test_a_failed_commit_is_an_error_not_a_quiet_success"
LOCK_PROBE = "test_the_index_is_read_and_written_under_a_lock_another_process_honours"
LOCKED = (
    "    with _REPOSITORY_LOCK, _open_repository(repo_root) as repo, _publish_lock(repo):\n"
    "        written = _write_recipe_file(repo_root, relative_path, data)\n"
    "        _stage_and_commit(repo, path, written, data, message)\n"
)

#: (slug, what the plant does, [(old, new)], test files, the tests that must go red)
PLANTS = [
    ("write-removed", "the commit never written: `if not unchanged:` -> `if False:`",
     [("    if not unchanged:\n", "    if False:  # PLANT\n")], [REPO_TESTS, COMMIT_TESTS],
     ["test_publish_writes_a_commit_real_git_reads",
      "test_a_second_publish_keeps_the_first_in_the_history",
      "test_the_file_is_committed_at_the_path_the_registry_row_will_name"]),
    ("planted-git-call", "a `git status` exec after the commit in commit_recipe_file",
     [("        await asyncio.to_thread(_commit_file, repo_root, relative_path, data, message)\n",
       "        await asyncio.to_thread(_commit_file, repo_root, relative_path, data, message)\n"
       "        await (await asyncio.create_subprocess_exec(\"git\", \"status\", cwd=repo_root))"
       ".wait()  # PLANT\n")], [REPO_TESTS],
     ["test_publish_never_execs_a_binary", "test_the_module_names_no_process_api"]),
    ("identical-bytes-committed", "identical bytes committed again: `unchanged = committed == "
     "blob.id` -> `unchanged = False`",
     [("            unchanged = committed == blob.id\n", "            unchanged = False  # PLANT\n")],
     [REPO_TESTS, COMMIT_TESTS],
     ["test_republishing_identical_bytes_makes_no_commit",
      "test_committing_the_same_bytes_again_is_not_an_error"]),
    ("broad-except-removed", "a dulwich or filesystem failure left untyped: `except Exception` "
     "-> `except ZeroDivisionError`",
     [("    except Exception as exc:  # dulwich", "    except ZeroDivisionError as exc:  # dulwich")],
     [REPO_TESTS], ["test_a_failed_write_is_a_typed_error_not_a_bare_500"]),
    ("index-not-written", "the index never written: `index.write()` -> `pass`",
     [("    index.write()\n", "    pass  # PLANT\n")], [REPO_TESTS, COMMIT_TESTS],
     ["test_publish_writes_a_commit_real_git_reads",
      "test_the_file_is_committed_at_the_path_the_registry_row_will_name"]),
    ("index-after-head", "the index written after HEAD moves (the order the review flagged)",
     [(INDEX_BLOCK, ""), (AFTER_REF, AFTER_REF + "\n" + INDEX_BLOCK)], [REPO_TESTS],
     ["test_a_failure_after_staging_leaves_nothing_committed"]),
    ("locks-removed", "no serialisation: neither the thread lock nor the publish flock taken",
     [("    with _REPOSITORY_LOCK, _open_repository(repo_root) as repo, _publish_lock(repo):\n",
       "    with _open_repository(repo_root) as repo:  # PLANT\n")], [REPO_TESTS],
     ["test_concurrent_publishes_each_commit_their_own_bytes",
      "test_the_index_is_read_and_written_under_a_lock_another_process_honours"]),
    ("refusal-discarded", "the compare-and-swap called and its answer discarded (the independent "
     "review, item 3): `if not repo.refs.set_if_equals(...)` -> `if repo.refs.set_if_equals(...) "
     "and False`",
     [("        if not repo.refs.set_if_equals(\n", "        if repo.refs.set_if_equals(\n"),
      (CAS_CLOSE, CAS_CLOSE.replace("        ):  # fmt: skip", "        ) and False:  # PLANT"))],
     [REPO_TESTS, COMMIT_TESTS], [FAKE_REFUSAL, RACE]),
    ("unconditional-head", "HEAD set whatever it holds: `set_if_equals(HEADREF, <head>, …)` -> "
     "`set_if_equals(HEADREF, None, …)`, which dulwich takes as no comparison",
     [("            HEADREF, head if head is not None else ZERO_SHA, commit.id,\n",
       "            HEADREF, None, commit.id,  # PLANT\n")], [REPO_TESTS], [RACE]),
    ("process-lock-removed", "the thread lock kept, the publish flock not taken: "
     "`fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)` -> `pass`",
     [("                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n", "                pass  # PLANT\n")],
     [REPO_TESTS],
     ["test_the_index_is_read_and_written_under_a_lock_another_process_honours"]),
    ("porcelain-commit", "the commit made by dulwich's worktree commit, which reads the config "
     "and runs the hooks in .git/hooks (the independent review, item 2)",
     [("    if not unchanged:\n",
       "    if not unchanged:\n        repo.get_worktree().commit(message=message.encode(), "
       "committer=_COMMIT_IDENTITY, author=_COMMIT_IDENTITY)  # PLANT\n        return\n")],
     [REPO_TESTS], ["test_publish_never_execs_a_binary"], "'.git/hooks/pre-commit'"),
    ("porcelain-signed-commit", "the same worktree commit with its hooks skipped, for a commit "
     "with a parent (the second publish, after the config is planted, since dulwich runs "
     "post-commit even with no_verify), so it reaches the signer `commit.gpgsign` and "
     "`gpg.program` name",
     [("    if not unchanged:\n",
       "    if not unchanged and parent is not None:  # PLANT\n"
       "        repo.get_worktree().commit(message=message.encode(), "
       "committer=_COMMIT_IDENTITY, author=_COMMIT_IDENTITY, no_verify=True)  # PLANT\n"
       "        return\n    if not unchanged:\n")],
     [REPO_TESTS], ["test_publish_never_execs_a_binary"], "trap.sh', '--detach-sign'"),
    ("staged-through-filters", "the recipe staged by dulwich's worktree stage, which applies "
     "the `.gitattributes` filter the config names",
     [("    repo.object_store.add_object(blob)\n",
       "    repo.get_worktree().stage([path])  # PLANT\n    repo.object_store.add_object(blob)\n")],
     [REPO_TESTS], ["test_publish_never_execs_a_binary"], "trap.sh"),
    ("id-unchecked", "neither the id's pattern nor dulwich's path check asked",
     [("    if _RECIPE_ID.fullmatch(recipe_id) is None:\n", "    if False:  # PLANT\n"),
      ("    if not validate_path(relative_path.encode(\"utf-8\")):", "    if False:  # PLANT")],
     [REPO_TESTS], ID_CASES),
    ("id-pattern-only-removed", "the id's pattern not asked, dulwich's path check kept: the ids "
     "that check alone lets through (`a/b`, `..` as `recipes/...yaml`, `.hidden`, ``); the "
     "`..`, `.git` and `../..` elements it refuses itself stay refused",
     [("    if _RECIPE_ID.fullmatch(recipe_id) is None:\n", "    if False:  # PLANT\n")],
     [REPO_TESTS], [ID_CASES[3], ID_CASES[4], ID_CASES[5], ID_CASES[6]]),
    ("directory-link-followed", "a symbolic link followed at `recipes/`: `O_NOFOLLOW` dropped from "
     "the directory's open",
     [("os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)",
       "os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)  # PLANT")], [REPO_TESTS],
     ["test_a_symlinked_recipes_directory_is_refused"]),
    ("file-link-replaced", "a symbolic link where the file goes not refused: "
     "`if not stat.S_ISREG(...)` -> `if False`",
     [("            if not stat.S_ISREG(existing.st_mode):\n", "            if False:  # PLANT\n")],
     [REPO_TESTS], ["test_a_symlinked_recipe_file_is_refused"]),
    ("lock-narrowed-to-the-swap", "the publish flock taken around the compare-and-swap alone "
     "(the independent re-review, item 3): not over the write, the index or the commit",
     [(LOCKED, LOCKED.replace(", _publish_lock(repo):", ":  # PLANT")),
      ("        if not repo.refs.set_if_equals(\n",
       "        with _publish_lock(repo):  # PLANT\n            moved = not repo.refs.set_if_equals(\n"),
      (CAS_CLOSE, CAS_CLOSE.replace("        ):  # fmt: skip", "            )\n        if moved:  # PLANT"))],
     [REPO_TESTS], [LOCK_PROBE]),
    ("lock-after-the-write", "the publish flock taken after the recipe file is written: over the "
     "index and the commit only",
     [(LOCKED, LOCKED.replace(", _publish_lock(repo):", ":  # PLANT").replace(
         "        _stage_and_commit(", "        with _publish_lock(repo):\n            _stage_and_commit("))],
     [REPO_TESTS], [LOCK_PROBE]),
    ("lock-file-link-followed", "the lock file opened following a link: `O_NOFOLLOW` dropped",
     [("os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC", "os.O_RDWR | os.O_CREAT | os.O_CLOEXEC")],
     [REPO_TESTS], ["test_a_linked_publish_lock_is_refused"]),
    ("init-in-place", "first use initialises the repository in place, as before the round-2 "
     "fix: a rival's repository and this one's collide",
     [("        repo = _initialise(repo_root)\n",
       "        repo_root.mkdir(parents=True, exist_ok=True)  # PLANT\n"
       "        repo = Repo.init(str(repo_root))\n"
       "        repo.refs.set_symbolic_ref(HEADREF, Ref(b\"refs/heads/main\"))\n")],
     [REPO_TESTS], ["test_a_rival_making_the_repository_first_is_joined_not_refused"]),
    ("init-reads-user-config", "first use initialised with the user's and the system's config",
     [("Repo.init(str(making), config=StackedConfig([ConfigFile()]))",
       "Repo.init(str(making))")],
     [REPO_TESTS], ["test_a_fresh_repository_is_on_main_whatever_the_user_s_config_says"],
     "read the user's or the system's git config"),
    ("index-reads-user-config", "the index opened with the whole config stack: "
     "`open_index(config=ConfigFile())` -> `open_index()`",
     [("    index = repo.open_index(config=ConfigFile())  # its settings from no config, not the user's",
       "    index = repo.open_index()  # PLANT")],
     [REPO_TESTS], ["test_a_fresh_repository_is_on_main_whatever_the_user_s_config_says"],
     "read the user's or the system's git config"),
    ("worktree-unchecked", "a config naming another worktree not refused",
     [("    if repo.bare or Path(repo.path).resolve() != repo_root.resolve():",
       "    if False:  # PLANT")],
     [REPO_TESTS], ["test_a_repository_whose_config_names_another_tree_is_refused"]),
    ("lock-waits-forever", "the publish flock waited for without limit: `LOCK_NB` dropped",
     [("fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)", "fcntl.flock(fd, fcntl.LOCK_EX)  # PLANT")],
     [REPO_TESTS], ["test_a_publish_held_off_too_long_is_refused_not_hung"], "DID NOT RAISE"),
    ("sweep-removed", "a crash's temporary file never swept",
     [("            if _TEMPORARY.fullmatch(left):", "            if False:  # PLANT")],
     [REPO_TESTS], ["test_a_temporary_file_a_crash_left_is_swept"]),
    ("id-pattern-narrowed", "the id pattern narrowed to lower-case words: a ULID refused",
     [('_RECIPE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")',
       '_RECIPE_ID = re.compile(r"[a-z][a-z0-9-]{0,199}")  # PLANT')],
     [REPO_TESTS], [f"test_an_id_of_the_shapes_the_studio_mints_is_accepted[{case}]"
                    for case in ("01JC5Q8K3ZP6V2T9XR4W7HMNBD", "a_b.c-1", "9")]),
]

def run(files: list[str]) -> str:
    done = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
         "-q", "-rA", *files],
        cwd=CORE, capture_output=True, text=True, env={**os.environ, "COLUMNS": "400"},
    )  # fmt: skip
    keep = ("PASSED", "FAILED", "ERROR")
    out = done.stdout.replace("\x00", "\\x00")  # one id case holds a NUL
    lines = [line for line in out.splitlines()
             if line.startswith(keep) and not line.startswith("ERROR  ")]  # fmt: skip
    return "\n".join(lines + [out.strip().splitlines()[-1]])


def main() -> int:
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=CORE, capture_output=True, text=True
    ).stdout.strip()
    original = PUBLISH.read_bytes()
    missed = []
    for n, (slug, what, edits, files, must_fail, *reason) in enumerate(PLANTS, start=1):
        text = original.decode()
        for old, new in edits:
            assert text.count(old) == 1, (slug, old)
            text = text.replace(old, new)
        PUBLISH.write_text(text)
        try:
            out = run(files)
        finally:
            PUBLISH.write_bytes(original)
        failed = {line.split("::")[-1].split(" ")[0] for line in out.splitlines()
                  if line.startswith("FAILED")}  # fmt: skip
        absent = [t for t in must_fail if t not in failed]
        # Where a plant names the reason, a failure for any other reason does not count (rule 15).
        if reason and not any(reason[0] in line for line in out.splitlines()
                              if line.startswith("FAILED")):  # fmt: skip
            absent.append(f"the reason {reason[0]!r}")
        missed += [(slug, t) for t in absent]
        (HERE / f"red-{n}-{slug}.txt").write_text(
            f"# head {head}; plant: {what}\n# command: pytest -q -rA {' '.join(files)}\n"
            f"# must fail: {', '.join(must_fail)}"
            f"{'; for the reason ' + repr(reason[0]) if reason else ''}"
            f"; all failed: {'yes' if not absent else absent}\n"
            f"{out}\n"
        )
    assert PUBLISH.read_bytes() == original
    green = run([REPO_TESTS, COMMIT_TESTS, IMAGE_TESTS])
    (HERE / "green.txt").write_text(f"# head {head}; no plant\n{green}\n")
    print("missed:", missed or "none")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
