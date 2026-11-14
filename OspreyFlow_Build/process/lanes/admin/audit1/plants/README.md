# Audit 1 plants (ADR-148 Amendment 16)

Each plant is one violation, in the shape the code has, run alone against its test with a fresh
`PYTHONPYCACHEPREFIX` (the orchestrator's rule, 13 Nov), offline on closed ports, then restored. All 16 red.
`replant.py <out dir>` re-runs them from `OspreyFlow_Core`. The live plant (the store's tenant guard in
`owner`) is run under the lease and recorded beside these.
