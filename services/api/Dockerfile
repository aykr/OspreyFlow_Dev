# services/api — the Conduit's API process, docs/07_BUILD_PLAN.md Phase 3.
# Standing rule (docs/07_BUILD_PLAN.md, "Standing rules for the whole
# build"): each service gets its own image, and a `trivy image` CI scan,
# in the phase that creates it — not batched into Phase 8.
#
# Unlike services/ingest's batch image, this is a long-running server:
# `03_CONDUIT_MIDDLEWARE.md` §1, "stateless... kill one mid-investigation
# and the analyst notices nothing" — nothing in this image or its startup
# sequence holds session state; every request re-derives what it needs
# from ArcadeDB, Valkey and Postgres.
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv==0.5.14

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY packages ./packages
COPY services ./services
# **`scripts/` is not optional for this image.** `services/api/app.py` imports
# `scripts.build_local_basemap` and `scripts.verify_map` at module top level — the geospatial
# admin routes added in round 09 — so without this the Conduit cannot import at all and the
# container crash-loops on `ModuleNotFoundError: No module named 'scripts'`. Found by round 13's
# clean install, the first time a rendered `local-lite` deployment actually reached `up` on this
# machine; every earlier attempt stopped at Preflight's memory floor, so nothing had exercised it.
# `harness/Dockerfile` already carries `scripts/` for the same reason.
COPY scripts ./scripts
# **Round 13bf.** Connector profiles are data the Conduit reads at import
# (`schemas.ingest.CONNECTOR_CATALOGUE`), not code, so nothing above pulls them in — and without
# them a rendered deployment reports *every* connector unavailable, `generic-csv` included, which
# is worse than the gap that mechanism was built to close. The same class
# `tests/test_image_imports_are_carried.py` already catches for modules;
# `tests/test_connectors_are_carried_into_the_image.py` is the case for this one.
COPY connectors ./connectors
COPY recipes ./recipes

FROM python:3.12-slim

# Base-image OS packages lag the upstream image's own last-published point
# release; picking up current Debian security patches at build time is
# what keeps `trivy image` (below) a real gate rather than permanently red
# on packages this service does not touch.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# **`git`, because the Conduit shells out to it and the image did not have it.**
# `09_INGEST_STUDIO.md` §6: "Publishing writes the recipe to version control, not only to the
# database. The studio is the editor; the repository is the record." `services/api/studio_publish.
# py` implements that with `asyncio.create_subprocess_exec("git", ...)`, so the binary is a
# runtime dependency of the Conduit in exactly the way a Python package is — and it was absent
# from every image this project has ever built. Publish returned a bare 500
# (`FileNotFoundError` from the exec) in every rendered deployment, while
# `tests/ingest/test_studio_publish_pipeline.py` passed throughout because it runs on the host,
# where `git` exists and the test `git init`s its own repository. Round 13bf, found walking the
# chain over the wire. `tests/test_connectors_are_carried_into_the_image.py` is what fails if it
# is dropped again.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 osprey
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/packages ./packages
COPY --from=builder /app/services ./services
COPY --from=builder /app/scripts ./scripts
COPY --from=builder /app/connectors ./connectors
COPY --from=builder /app/recipes ./recipes

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app:/app/packages" \
    PYTHONUNBUFFERED=1 \
    HOME="/app"

# `analytics_duckdb/schema.py`'s `load_extension("spatial")` (Phase 5a,
# polygon geometry storage) must never touch the network at runtime — this
# platform's tier 1 default and CI both assume no network access once a
# deployment is up (`00_ARCHITECTURE.md` §1.2, `07_BUILD_PLAN.md` standing
# rule 3). Installing it here, at build time, populates DuckDB's own
# extension cache under `$HOME/.duckdb` so the runtime `load_extension`
# call only ever reads a local file — it never re-installs.
RUN /app/.venv/bin/python -c "import duckdb; duckdb.connect().install_extension('spatial')" \
    && chown -R osprey:osprey /app

# The deployment's data root, created here and owned by the runtime user.
# Docker initialises a named volume from the image's own contents at the
# mount point: if the directory does not exist in the image, the volume is
# created root-owned and this non-root process cannot write its analytics
# DuckDB file into it. Creating it with the right owner is what makes
# `osprey-data` usable rather than merely mounted.
RUN mkdir -p /var/lib/osprey/data && chown -R osprey:osprey /var/lib/osprey

USER osprey
EXPOSE 8000

# `GET /healthz` — `03_CONDUIT_MIDDLEWARE.md` §3.0, the owner's decision of
# 24 September 2026. Without a declared health check `docker compose up
# --wait` has nothing to wait on, which is what stopped the scripted deploy
# reaching its own exit criterion (ADR-049 Stage 2 §3).
#
# Liveness, not readiness: this asks whether the process is up, and it
# deliberately stays true when every store is down. `start-period` is
# generous because this process applies the graph schema at startup before
# it serves anything.
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=6 \
    CMD ["/app/.venv/bin/python", "-c", \
         "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status==200 else 1)"]

ENTRYPOINT ["uvicorn", "services.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
