# v052-identities' plants, re-run at 7a84543

Every offline plant of v052-identities, written against the code at 7a84543 and re-run with a fresh
`PYTHONPYCACHEPREFIX` for each pytest invocation (the orchestrator's rule of 13 November: a stale `.pyc` can run the
previous plant's bytecode). `replant.py` holds each plant (the file, the line replaced, its replacement, the test file
and `-k`) and wrote the records here. All 30 are red, the Glass's under vitest. These are the records the
ready-to-merge cites; the earlier ones in `v052/` and `v052/review/` stand as what was seen at the time. The two
plants that need PostgreSQL (the case gate opened, revoke_everywhere deleting nothing) and the tenant plant run on the
lane's stack: `live2/`.
