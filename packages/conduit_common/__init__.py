"""Shared, adapter-independent Conduit logic.

`services/api` (the API process) and `services/ingest` (a Conduit worker
pool — `03_CONDUIT_MIDDLEWARE.md` §2) both write through `GraphPort`, so
anything the Conduit owns that isn't specific to one of them lives here
rather than being duplicated.
"""
