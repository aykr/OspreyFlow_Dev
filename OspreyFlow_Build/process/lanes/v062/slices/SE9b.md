# SE9b: the deletion statements' parameter name (the owner, 23 November 2026, "yes, as you propose")

**Build SE9 (the owner's plan), a fix to SE9's own merge `2e13b10`.** GitHub's conformance job on `2e13b10` (run `45242082174`) has 80 failing live tests, all with one database error:

```
ArcadeDB error 400 … CommandSQLParsingException … SQL syntax error at line 1, column 68: mismatched input ',' expecting {<EOF>, ';'}
UPDATE `mx_COMMUNICATED_WITH` SET reverted = true, reverted_at = :at, reverted_by = :by, withdrawn_by_load = null WHERE id IN :ids
```

The parse stops at the comma straight after `:at`. SE9's commit `3605498` added the parameter `:at` to three statements in `OspreyFlow_Core/packages/adapters/graph_arcadedb/adapter.py` (the deleting write with `withdrawn_by_load = null`; the revert-by-load with `:load`; the dataset withdrawal with `:w`; `grep -n ":at" ` finds them). The Mac's gate and the server both skip the live step, which is why nothing caught it before GitHub. **The conductor's reading, not yet proved, is that `at` is a reserved word in ArcadeDB's SQL, so a parameter of that name cannot be written.**

## What you do

1. **Prove the cause on the live database first, before changing any code.** Take the stack lease (`OspreyFlow_Build/scripts/stack_lease.sh`, rule 14), start a **throwaway ArcadeDB of your own on a free high port** (never the owner's `osprey-local-lite-*` deployment, never port 2480), and run the failing statement shape against it: once with the parameter named `at` (it must be refused with the error above) and once with another name such as `when_at` and the same value (it must be accepted). **If the cause turns out to be anything else, STOP and tell the conductor: do not guess a second fix.** Bring the stack down and release the lease when you finish. Give the exact commands you ran in your report.
2. **Rename the parameter in the three statements only**, the SQL text and the `params` key together. **Nothing else: no change to what is written, to `_utc_text`, to any other statement, to the spec, or to any test beyond what the rename needs.** Existing fake-driven tests that name the key `at` change with it, and you say which.
3. **Tests, red first, at the shape the code really sends (rule 15):**
   - **The acceptance test (pure, no database; a new file):** it runs the three code paths through a client that records each statement and its parameters, and fails when any statement names a parameter that the live proof in step 1 showed the database refuses (the reserved word you proved, as a named constant with a comment saying where the proof is). It must fail on `2e13b10`'s code and pass after the rename. **A fake that accepts what the real database refuses is exactly how this reached main: the test says which names the real database refuses.**
   - **A live twin (a new file, marked live like its neighbours, owed until a run):** the three statements run for real against a node, an edge and a dataset withdrawal, and the rows read back with `reverted_at` and `reverted_by` set. It runs from the builder under your own lease, and in GitHub's conformance job.
4. **The scan-map row** for any new test that walks a folder: the conductor writes it on main (never into `scan_rows/` yourself). A test that walks nothing needs no row.
5. **Before your report:** run the pure test, the existing tests that name the deletion statements (`test_revert_elements_by_type.py`, `test_write_onto_a_reverted_node.py`, `test_count_deleted_visible.py`, `test_snapshot_withdrawal.py`), the live twin from your own stack, `ruff check` and `ruff format --check` on every file changed, and the citation check.

## Never merge another part's unmerged tip (the owner, 23 November 2026)

**Never merge another part's unmerged tip, or any branch but main, into your branch.** Take main in when the line tells you to, and nothing else. If your part needs another part's change that has not merged, stop and tell the conductor.

## Out of scope

Any other SQL in the adapter; the SE9 spec; the 80 other live failures if they have a different cause (list them in your report if some remain after the rename: they are not this part's to fix); the protected files. **A finding that names a key, a credential or a security rule is stopped and reported, never accepted narrower.**
