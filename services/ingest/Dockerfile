# services/ingest — docs/07_BUILD_PLAN.md Phase 2. First Dockerfile in the
# build: the standing rule (docs/07_BUILD_PLAN.md, "Standing rules for the
# whole build") is that each service gets its own image, and a `trivy
# image` CI scan, in the phase that creates it — not batched into Phase 8.
#
# A batch job image (ADR-013: batch and micro-batch only, no streaming
# lane) — one container run loads one recipe against one source file, then
# exits. Not a persistent server.
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

RUN useradd --create-home --uid 10001 mantis
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/packages ./packages
COPY --from=builder /app/services ./services

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app:/app/packages" \
    PYTHONUNBUFFERED=1

USER mantis
ENTRYPOINT ["python", "-m", "services.ingest"]
