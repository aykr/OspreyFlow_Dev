# Slice CO3b · CO3 · `test_ws_ticket.py` reads the live Valkey at `VALKEY_PORT`, not a fixed 6379 (a test-only part; the owner, 26 November 2026, from away/live-A)

- **Build id:** CO3 (the WebSocket ticket) · **Dial setting:** balanced · **Rounds limit:** 4 · **After:** nothing (it starts after the queue: GG4c last)
- **Test-only:** no product file changes; no assertion changed.

## Why (away/live-A, commit `88e391b4b`)

The `valkey` fixture opened `Valkey(host="localhost", port=6379, db=0)`. 6379 is stack a's Valkey; from any other stack
(b to g hold 6380 to 6385) or a run with the store ports pinned, the port guard refuses it, so the five cases could pass
only on stack a or in CI. live-A's commit reads `VALKEY_PORT` (6379 when unset), as `test_valkey_store.py` and its
neighbours do: red on its throwaway Valkey (5 refused at `::1:6379`), green after (5 passed). Its evidence files are under
`process/lanes/v062/away/live-A/G50_ws_ticket_fixed/`.

## Round 1

1. **Take the one commit:** `git cherry-pick 88e391b4b` from the local branch `away/live-A` (the owner's word: that commit
   alone; nothing else from the branch). Keep its evidence files as they are.
2. **A pure acceptance test, red first** (the Mac is offline, so the store file cannot be the proof here):
   `OspreyFlow_Build/tests/services/api/test_ws_ticket_reads_valkey_port.py` sets `VALKEY_PORT` to an unused value and
   checks the fixture's client takes it, **without connecting** (read the client's connection settings; say how). Red on
   main, before the cherry-pick; green after. Plant: the fixed 6379 put back in the real file, red; restored (rule 15).
3. Name in your report any other test under `OspreyFlow_Build/tests/services/api/` that opens a store at a fixed port.
   **List them, change nothing** (several name 6379 in other ways; the owner decides).

## How it is judged

The frozen checks are pure. The store file itself is judged by the server's early warning and by GitHub's `conformance`
job after the merge.

## Checks

The new test; `pytest --collect-only` on `test_ws_ticket.py`; `ruff check .`.

## Out of scope

Product code, the port guard, every other test file, the rest of `away/live-A`.

## The conductor's answer after round 1's stop (26 November 2026, 13:25 UTC)

`test-file-coverage-check` reads a test that imports the Valkey client as a store test. **(a): the new test imports
neither `Valkey` nor any store client, not even for type hints.** Read the fixture's port another way (call the fixture
function's body with a stand-in for the client class, or read the source by its syntax tree; say which), keep the plant,
and keep it red first. Do not change the checker or any list.
