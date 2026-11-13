# The committed osprey.yaml, read from the commit (the orchestrator's question after the pin merge), 13 November 2026

Branch `lane/platform-b-yaml`, from main a68c710.

## What the test read

Not the main checkout. `test_the_committed_osprey_yaml_still_validates` reads its own worktree's
`OspreyFlow_Core/osprey.yaml` (`tools.layout.REPO / "osprey.yaml"`). But `scripts/lanes_launch.sh`'s
`setup` (lines 124–126) copies the owner's uncommitted `osprey.yaml` from the main checkout into every
lane worktree and marks it `--skip-worktree`. `git ls-files -v` shows `S`, and `git status` shows
nothing. Here the copy is byte-identical to the main checkout's (`default: osm-local-great-britain`);
`HEAD`'s says `osm-local`. At the time of writing, 13 worktrees under `~/dev/osprey-wt` carry the flag.

Two more tests read the same path as "the committed config", and so tested the owner's config in a
lane: rule 9's `test_demo_osprey_config_is_tier_1_only.py` (three cases) and `test_osprey_bundle.py`'s
`bundle_config` fixture. In this lane they passed, because the owner's providers are open, but
they were checking the wrong file.

## The fix

`tests/committed.py`: `committed_text(path)` (`git show HEAD:./<name>`) and `committed_copy(path, into)`
for loaders that take a path. There is deliberately no fallback to the working copy: if git can't
answer, it raises. All three readers use it. The launcher is unchanged; its copy is deliberate (the
owner's config in a lane).

## Red then green

| | Result |
| --- | --- |
| main a68c710's `test_the_committed_osprey_yaml_still_validates`, in this lane | red: `assert 'osm-local-great-britain' == 'osm-local'` |
| plant: `committed_text` returns `path.read_text()`, i.e. how the tests read before | red: `test_a_skip_worktree_copy_is_not_what_it_reads` (a git repo built the way the lanes are: committed, working copy changed, `--skip-worktree`, `git status` empty), `test_a_file_git_does_not_hold_is_refused_not_read_from_disk`, and the schema case |
| restored | green: 17 passed |
| the four files in full | 77 passed, 1 skipped |

test-file-coverage-check and citation-check pass. Ruff is clean on the changed lines: test_osprey_bundle.py went from 2 to 0 errors, and test_deployment_schema.py's remaining 11 were already on main (12 there).
