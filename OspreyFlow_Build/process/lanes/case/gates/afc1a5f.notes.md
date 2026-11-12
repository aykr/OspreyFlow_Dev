# afc1a5f: every failure explained

All on the test server through `stack_lease.sh offline case` (no stack, no lease), lane/case-p9 on main 816ccf7
(L1.9 part 2 in).

**make -k ci (exit 0).** cp-policy-check, unfiltered: development-sources 57, development 57, poc 49,
production-bedrock 64, production 64 manifests, 0 violation(s) each. harness-a11y in slot 14 (`OSPREY_PORTS_SLOT=14`):
34 passed. The run at ac19576 before it failed one check, mypy on the set's finish time (a name `take` already used
for a bool), fixed in afc1a5f.

**make test (1 failed, 12459 passed, 2 xfailed).**
- `test_webapp_preflight.py::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`: the server has a GPU (known,
  not this branch's). OpenSearch's memory case passed this run.
- The 2 xfailed (strict): `test_backups_rows.py`'s restore and restore-claims rows, held until `P9_rows.diff`.

**make live-collect (exit 0)**, run on its own, since `make test` stops at its first failure (the orchestrator's
addition).

With the three diffs applied (`p9_cp_policy_merged.r2.txt`, at a06b145; afc1a5f changes only a variable's name and
its plant's anchor): cp-policy-check 0 violation(s) on all five fixtures, 717 passed none held, P9's plants 96 of 96
red, P9_rows.diff's 5 of 5. Kind: `p9_kind_live_restore.r4.json` (lease b).
