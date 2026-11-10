# services/api — the Conduit's API process, process/07_BUILD_PLAN.md Phase 3.
# Standing rule (process/07_BUILD_PLAN.md, "Standing rules for the whole
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

# ADR-147 Amendment 2 (the owner's ruling 1 of 9 November 2026, option A): the tier-1 basemap build
# (planetiler) runs in the Conduit, so the image carries a Java 21 runtime: Eclipse Temurin, under
# GPL-2.0 with the Classpath exception, the licence register's one recorded runtime exception
# (`00_ARCHITECTURE.md` §7; `make licence-check` reads the label below). jlinked to the modules a JVM
# program such as planetiler uses, without its tools, debug symbols or headers; the official image
# pinned by its digest (the multi-architecture index, so arm64 and amd64 build alike): Temurin
# 21.0.13+9, October 2026's update. trivy does not see a jlinked runtime, so the version label below
# is held to the built image's /opt/java/release and `java -version` (CI's `trivy-image-api` job),
# and the digest to the one `eclipse-temurin:21-jdk` resolves to on Docker Hub now (Build's
# `make ci`), by the build folder's `java_runtime_check`; repin the digest and the label together.
FROM eclipse-temurin:21-jdk@sha256:ebfbb18d11ff163ee83b21258acf12248af48d22a0fdfdc68fa1a1516c05976a AS java
RUN jlink \
      --add-modules java.base,java.compiler,java.desktop,java.instrument,java.logging,java.management,java.naming,java.net.http,java.prefs,java.scripting,java.security.jgss,java.sql,java.xml,jdk.crypto.ec,jdk.jfr,jdk.management,jdk.unsupported,jdk.zipfs \
      --strip-debug --no-man-pages --no-header-files --compress=zip-6 \
      --output /opt/jre

FROM python:3.12-slim

# Base-image OS packages lag the upstream image's own last-published point
# release; picking up current Debian security patches at build time is
# what keeps `trivy image` (below) a real gate rather than permanently red
# on packages this service does not touch.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# No `git`: publishing commits a recipe in-process with dulwich (Apache-2.0), so nothing this image
# carries execs the binary, which is GPL-2.0-only (the owner's ruling of 9 November 2026; ADR-140
# Amendment 17). `tests/test_connectors_are_carried_into_the_image.py` fails if `git` is installed
# again, and `make licence-check` names it as an offender.

COPY --from=java /opt/jre /opt/java
LABEL org.ospreyflow.runtime.java.licence="GPL-2.0-only WITH Classpath-exception-2.0"
LABEL org.ospreyflow.runtime.java.version="21.0.13+9"

RUN useradd --create-home --uid 10001 osprey
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/packages ./packages
COPY --from=builder /app/services ./services
COPY --from=builder /app/scripts ./scripts
COPY --from=builder /app/connectors ./connectors
COPY --from=builder /app/recipes ./recipes

ENV PATH="/app/.venv/bin:/opt/java/bin:${PATH}" \
    JAVA_HOME="/opt/java" \
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
# ADR-135 Amendment 2 decision 2: the models file's folder. A named volume takes this folder's
# owner and mode on first mount, so the Conduit's user can write it on any host.
RUN mkdir -p /run/osprey/model-settings && chown osprey:osprey /run/osprey/model-settings \
    && chmod 700 /run/osprey/model-settings
# ADR-147 decision 1: the maps file's and the map key file's folder, made the same way.
RUN mkdir -p /run/osprey/map-settings && chown osprey:osprey /run/osprey/map-settings \
    && chmod 700 /run/osprey/map-settings

USER 10001:10001
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
