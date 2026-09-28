# services/ingest — process/07_BUILD_PLAN.md Phase 2. First Dockerfile in the
# build: the standing rule (process/07_BUILD_PLAN.md, "Standing rules for the
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

RUN useradd --create-home --uid 10001 osprey
WORKDIR /app

# `--chown` is not cosmetic here. `COPY` preserves the source file's mode, so a single
# restrictively-permissioned file anywhere in `packages/` or `services/` — one `0600` is enough —
# lands in the image owned by root and unreadable by `osprey`, and the container dies on import
# with a `PermissionError` naming a file nobody has touched. Found 24 September 2026 the first time
# this image was ever actually run (ADR-049 Stage 2 §5a): `packages/adapters/graph_arcadedb/
# naming.py` was `0600` on the builder's own machine. Git tracks it `100644`, so a fresh clone is
# unaffected and this was never a repository defect — which is exactly why it went unnoticed, and
# exactly why the image should not depend on every developer's umask. `services/api`'s image
# happens to be immune only by accident: its DuckDB extension step runs `chown -R` for an unrelated
# reason.
COPY --from=builder --chown=osprey:osprey /app/.venv ./.venv
COPY --from=builder --chown=osprey:osprey /app/packages ./packages
COPY --from=builder --chown=osprey:osprey /app/services ./services

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app:/app/packages" \
    PYTHONUNBUFFERED=1

USER osprey
ENTRYPOINT ["python", "-m", "services.ingest"]
