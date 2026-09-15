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

FROM python:3.12-slim

# Base-image OS packages lag the upstream image's own last-published point
# release; picking up current Debian security patches at build time is
# what keeps `trivy image` (below) a real gate rather than permanently red
# on packages this service does not touch.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 osprey
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/packages ./packages
COPY --from=builder /app/services ./services

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app:/app/packages" \
    PYTHONUNBUFFERED=1

USER osprey
EXPOSE 8000
ENTRYPOINT ["uvicorn", "services.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
