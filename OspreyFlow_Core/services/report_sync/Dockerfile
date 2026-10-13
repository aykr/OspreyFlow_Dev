# Report sync as an image of its own (`06_DECISIONS.md` ADR-111 Amendment 2; ADR-114 decision 9,
# Amendment 10 point 6): `python -m services.report_sync`, pulling each case's figures into the
# reporting mart. It reads the Conduit's settings (`services.api.config`), so it carries `packages`
# and `services`; nothing the Conduit needs only for its routes.
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
COPY --from=builder --chown=osprey:osprey /app/.venv ./.venv
COPY --from=builder --chown=osprey:osprey /app/packages ./packages
COPY --from=builder --chown=osprey:osprey /app/services ./services

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app:/app/packages" \
    PYTHONUNBUFFERED=1 \
    HOME="/app"

USER osprey
# The heartbeat check `__main__` describes: unhealthy once a pass has not finished in two intervals.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-m", "services.report_sync", "--health"]
ENTRYPOINT ["python", "-m", "services.report_sync"]
