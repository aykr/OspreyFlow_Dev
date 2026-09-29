"""The Conduit's API process — `spec/03_CONDUIT_MIDDLEWARE.md`.

Stateless FastAPI: session and working-set state live in Valkey, durable
state in the Vault, never in this process — kill one instance mid-session
and the analyst notices nothing (`03_CONDUIT_MIDDLEWARE.md` §1).
"""
