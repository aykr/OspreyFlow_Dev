# Slice AD1d · AD1 · test-file-coverage-check knows a test that starts its own private database is not a live-service test (the owner's ruling (c), 25 November 2026)

- **Build id:** AD1 (it unblocks AD1c, the key review's open items)
- **Dial setting:** balanced
- **Rounds limit:** 8
- **After:** nothing. **AD1c waits for this part to merge**, then imports `asyncpg` plainly.

## What

`OspreyFlow_Build/tools/test_file_coverage_check.py` classifies a test file that imports `asyncpg` (one of
`LIVE_SERVICE_MARKERS`, about line 105) as needing a shared live service, so it must be in both the `test` job's
ignore list and a live-service job in `ci.yml` (protected files). AD1c's new test starts **its own private
PostgreSQL** (`initdb` and `pg_ctl` in a temporary folder, removed at the end; skipping, saying so, where no `initdb`
exists) and needs no shared service. Its builder got past the check by importing `asyncpg` by name at run time, which
the owner refused: **no import is ever written to miss a check.**

1. **One shared helper** for a private, throwaway PostgreSQL: `OspreyFlow_Build/tests/private_postgres.py` (or the
   tests' existing helper folder, if there is one: read how tests share helpers today). It finds `initdb` the way
   AD1c's test does (the machine's own PostgreSQL: Homebrew's `postgresql@*`, `/usr/lib/postgresql/*/bin`), makes a
   data folder under the test's temporary folder, starts the server on a free port that `tests/port_guard.py` does
   not reserve, yields its address, and stops and removes it at the end, whatever the test did. Where no `initdb`
   exists, or the process is root, it skips **saying so**. **Never** the owner's deployment, the demo, the dev stack or
   any store port the lanes hold.
2. **The check:** a test file that imports `asyncpg` **and** uses that helper (by its real import, read from the
   file's `import` statements, as `_imported_names` already reads them), and has **no other live-service marker** and
   no `PostgresConfig.from_env()` call, is not live-service. Anything else stays as today.
3. **The words:** the check's message for a live-service file is unchanged; its docstring names the helper and why.

## Acceptance test

`OspreyFlow_Build/tests/test_test_file_coverage_private_database.py` (new, pure), red first, each case planted as the
check really receives it (a real file under its temporary tree, read through the same functions `main()` uses):
- a file importing `asyncpg` and the helper: **not** live-service (red today);
- a file importing `asyncpg` without the helper: live-service, as today;
- a file importing the helper and `ArcadeDBClient` (or any other marker): live-service;
- a file importing the helper and calling `PostgresConfig.from_env()`: live-service;
- a file that only **names** the helper in a docstring or comment, and imports `asyncpg`: live-service (the name in
  text is not the import);
- **the helper itself:** started, it answers on its port as a real PostgreSQL (a `SELECT 1`), its data folder is
  under the temporary folder, and after the test the process is gone and the folder removed; with no `initdb` on the
  path it skips with words naming `initdb`.

Show the check's new branch red: removed, the first case fails; and **planted with the helper test removed (any
file importing `asyncpg` treated as private)**, the second case fails (rule 15: the plant takes the shape the real
call site produces, not one a default branch would catch).

## Checks

`cd OspreyFlow_Core && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=$HOME/dev/osprey-acceptance/AD1d uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/test_test_file_coverage_private_database.py ../OspreyFlow_Build/tests/test_test_file_coverage_check.py ../OspreyFlow_Build/tests/test_doc_citations_check.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=$HOME/dev/osprey-acceptance/AD1d uv run --frozen ruff check .`; and `make -C OspreyFlow_Build test-file-coverage-check` green on the tree.

## Out of scope

`ci.yml`, the Makefile and their lists (protected); AD1c's own test (AD1c moves to the helper after this merges); any
other marker's meaning; the scan map. **If a private database cannot be told apart from a shared one by imports
alone, stop and say why: do not add a comment, name or flag a file can write to opt out.**
