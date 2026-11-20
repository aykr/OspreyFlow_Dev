"""The client names' hashed list reaches a slice's worktree without the owner (F5, the owner's ruling 4(d)).

slice_start.py copies OspreyFlow_Build/marketing_site/client_names.local.sha256 from the main checkout into the new
worktree when the main checkout has it, and only where git ignores it there (as the merge gate's bring_client_hashes
does); it says in words when the main checkout has none. The list is never committed.
"""
from __future__ import annotations

import hashlib

from test_gates import sh, started, world  # noqa: F401  (world is a fixture)

HASHES = "OspreyFlow_Build/marketing_site/client_names.local.sha256"


def ignore_it(w, ignored=True):
    (w["repo"] / ".gitignore").write_text("Claude outputs/\n" + (HASHES + "\n" if ignored else ""))
    sh("git commit -qam 'build: ignore the hashed list' --trailer 'Slice-Records: yes'", w["repo"], w["env"])


def test_slice_start_copies_the_hashed_list_into_the_worktree_where_git_ignores_it(world):
    w = world
    ignore_it(w)
    f = w["repo"] / HASHES
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(hashlib.sha256(b"a listed name").hexdigest() + "\n")
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert (wt / HASHES).read_text() == f.read_text()
    assert "client_names" not in sh("git status --porcelain --untracked-files=all", wt).stdout


def test_slice_start_says_in_words_when_the_main_checkout_has_no_hashed_list(world):
    w = world
    ignore_it(w)
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "no hashed client-name list" in p.stdout and not (wt / HASHES).exists(), p.stdout


def test_slice_start_never_copies_the_list_where_git_would_take_it(world):
    w = world
    ignore_it(w, ignored=False)
    f = w["repo"] / HASHES
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(hashlib.sha256(b"a listed name").hexdigest() + "\n")
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert not (wt / HASHES).exists() and "not ignored by git" in p.stdout, p.stdout
