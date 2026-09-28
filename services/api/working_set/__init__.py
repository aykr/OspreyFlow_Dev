"""The Working-Set Service — `spec/03_CONDUIT_MIDDLEWARE.md` §4, the most
important component in the Conduit (its own words). Server-side, capped,
delta-streamed (ADR-007); see `models.py` for the wire protocol,
`store.py` for the Valkey-backed storage, `service.py` for the
seed/expand/reconnect orchestration.
"""
