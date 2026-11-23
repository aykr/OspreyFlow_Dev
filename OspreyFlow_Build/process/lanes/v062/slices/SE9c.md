# SE9c: the deletion statements' reserved parameter name (SE9b's builder proved the word is `by`, not `at`; the conductor, 23 November 2026, 22:25 UTC)

**Build SE9 (the owner's plan), a fix to SE9's own merge `2e13b10`. It replaces SE9b, which stopped for the owner when its live proof found that the word the database refuses is `by`, not `at`.** SE9b's brief and the owner's word ("rename the parameter in the three statements only, a live test against a throwaway ArcadeDB under the stack lease, red first; prove the reserved-word reading on the live database; if the cause is something else, stop and tell me") stand. **The reading (a reserved word in ArcadeDB's SQL) is confirmed; the word is different, and the owner is told in the morning report. The conductor cut this part rather than wait for him, because main has 80 live tests red on it and the change is the same rename of one parameter name in the same three statements; he can retire it if he disagrees.**

GitHub's conformance job on `2e13b10` (run `45242082174`) has 80 failing live tests with one database error:

```
ArcadeDB error 400 … CommandSQLParsingException … SQL syntax error at line 1, column 68: mismatched input ',' expecting {<EOF>, ';'}
UPDATE `mx_COMMUNICATED_WITH` SET reverted = true, reverted_at = :at, reverted_by = :by, withdrawn_by_load = null WHERE id IN :ids
```

SE9's commit `3605498` added `:at` and `:by` named parameters to three statements in `OspreyFlow_Core/packages/adapters/graph_arcadedb/adapter.py` (about lines 2052, 2081 and 2189: the deleting write with `withdrawn_by_load = null`; the revert by load with `:load`; the dataset withdrawal with `:w`). The Mac's gate and the server skip the live step, so nothing caught it before GitHub.

## What SE9b's builder proved live (its report, 23 November 2026; throwaway ArcadeDB on its own stack, lease released afterwards)

- The statement with `:when_at` and `:by` is **refused**, with the same error as GitHub's job.
- The statement with `:at` and `:whom` (any other name for the second parameter) is **accepted**.
- `:at` and `:when_at` on their own are accepted. **`:by` on its own is refused** (`no viable alternative at input 'by'`).

**So the refused word is `by`.** (`:at` is not reserved; the earlier reading of the error, which stops at the comma after `:at`, was the conductor's.)

## What you do

1. **Re-prove it yourself first, before changing any code** (a few minutes: SE9b's proof is a lead, not a fact for you). Take the stack lease (`OspreyFlow_Build/scripts/stack_lease.sh`, rule 14), start a **throwaway ArcadeDB of your own on a free high port** (never the owner's `osprey-local-lite-*` deployment, never port 2480), and run the failing statement shape: once with `:by`, once with another name for the same value. **If the cause turns out to be anything else, STOP and tell the conductor: do not guess a second fix.** Bring the stack down and release the lease when you finish. Give the exact commands you ran in your report.
2. **Rename `:by` in the three statements only**, the SQL text and the `params` key together, to a name the proof shows is accepted (for example `:whom`). **Leave `:at` as it is.** Nothing else: no change to what is written, to `_utc_text`, to any other statement, to the spec, or to any test beyond what the rename needs. Existing fake-driven tests that name the key `by` change with it, and you say which. **If `by` is used as a parameter name in any other statement of the adapter, list each in your report and leave it (it may be fine in a context the database accepts: prove it live before touching it).**
3. **Tests, red first, at the shape the code really sends (rule 15):**
   - **The acceptance test (pure, no database; a new file named in the row):** it runs the three code paths through a client that records each statement and its parameters, and fails when any statement names a parameter the live proof showed the database refuses (`by`, as a named constant with a comment saying where the proof is). It must fail on `2e13b10`'s code and pass after the rename. **A fake that accepts what the real database refuses is exactly how this reached main: the test says which names the real database refuses.**
   - **A live twin (a new file, marked live like its neighbours, owed until a run):** the three statements run for real against a node, an edge and a dataset withdrawal, and the rows read back with `reverted_at` and `reverted_by` set. It runs from your own lease and stack, and in GitHub's conformance job.
4. **The scan-map row** for any new test that walks a folder: the conductor writes it on main (never into `scan_rows/` yourself). A test that walks nothing needs no row.
5. **Before your report:** run the pure test, the existing tests that name the deletion statements (`test_revert_elements_by_type.py`, `test_write_onto_a_reverted_node.py`, `test_count_deleted_visible.py`, `test_snapshot_withdrawal.py`), the live twin from your own stack, `ruff check` and `ruff format --check` on every file changed, and the citation check.

## Never merge another part's unmerged tip (the owner, 23 November 2026)

**Never merge another part's unmerged tip, or any branch but main, into your branch.** Take main in when the line tells you to, and nothing else. If your part needs another part's change that has not merged, stop and tell the conductor.

## Out of scope

Any other SQL in the adapter; the SE9 spec; the 80 live failures if some have a different cause (list the ones that remain after the rename in your report: they are not this part's to fix); the protected files. **A finding that names a key, a credential or a security rule is stopped and reported, never accepted narrower.**
