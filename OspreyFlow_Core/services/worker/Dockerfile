# The job worker as an image of its own (`06_DECISIONS.md` ADR-114 decision 9, Amendment 10 point 6):
# `python -m services.api.worker_main`, the process the Conduit's lifespan also runs in Lite. Its
# code is the Conduit's — the job queue, the graph adapter, the handlers it names — so it carries
# `packages` and `services`, and nothing the Conduit needs only for its routes: no `scripts`, no
# connector profiles, no recipes, no `git`. Replicas are safe: each takes its consumer name from its
# own hostname (`worker_main.consumer_name`).
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv==0.5.14

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY packages ./packages
COPY services ./services

FROM python:3.12-slim

# Current Debian security patches at build time, so `trivy image` stays a real gate.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 osprey
WORKDIR /app
# `--chown`, as `services/ingest/Dockerfile` explains: a source file's own mode must not decide
# whether the worker can import it.
COPY --from=builder --chown=osprey:osprey /app/.venv ./.venv
COPY --from=builder --chown=osprey:osprey /app/packages ./packages
COPY --from=builder --chown=osprey:osprey /app/services ./services

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app:/app/packages" \
    PYTHONUNBUFFERED=1 \
    HOME="/app"

USER osprey
ENTRYPOINT ["python", "-m", "services.api.worker_main"]
