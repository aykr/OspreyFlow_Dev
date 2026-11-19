# apps/pages — the Glass's server-rendered pages: a Node service (ADR-152 decision 1).
#
# Unlike apps/workspace this does run a long-lived Node process of its own: it holds the person's
# session on the server and renders each page complete before sending it. Express, Nunjucks and helmet;
# no React, and nothing fetched from another address (ADR-152 decision 3).
#
# Three stages, on the Node version the workspace image's builder pins: one compiles the TypeScript, one
# installs only what the service needs at run time, and the last carries the compiled service and that
# and nothing else. The build context is `OspreyFlow_Core` (`-f apps/pages/Dockerfile .`), as for the
# workspace.
#
# Not yet in the renderer's images list or the compose output (a later slice wires it behind the front
# proxy), so nothing builds this image in CI yet.

FROM node:22-slim AS builder

WORKDIR /app

# The npm workspace root and every workspace's manifest: `npm ci` checks the lockfile against all of
# them, and this layer caches across source-only changes.
COPY package.json package-lock.json ./
COPY apps/workspace/package.json ./apps/workspace/
COPY apps/harness/package.json ./apps/harness/
COPY apps/pages/package.json ./apps/pages/
RUN npm ci --workspace apps/pages

COPY apps/pages ./apps/pages
RUN npm run build --workspace apps/pages

FROM node:22-slim AS runtime-deps

WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/workspace/package.json ./apps/workspace/
COPY apps/harness/package.json ./apps/harness/
COPY apps/pages/package.json ./apps/pages/
RUN npm ci --omit=dev --workspace apps/pages && npm cache clean --force

FROM node:22-slim

# The day's stamp (`harness/upgrade_stamp.py`): every build passes today's date, so this upgrade's
# layer is made again each day and a builder's cached copy cannot keep the distribution's old fixes.
ARG OSPREY_UPGRADE_STAMP=
RUN echo "distribution fixes as of ${OSPREY_UPGRADE_STAMP:-an unstamped build}" && apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

ENV NODE_ENV=production
WORKDIR /app
COPY --from=runtime-deps --chown=10001:10001 /app/node_modules ./node_modules
COPY --from=builder --chown=10001:10001 /app/apps/pages/dist ./apps/pages/dist
COPY --chown=10001:10001 apps/pages/package.json ./apps/pages/package.json

# ADR-148 decision 3: one numeric non-root user for all our images, so a platform that refuses a
# named user (`runAsNonRoot` cannot check a name) runs it as it is.
USER 10001:10001
# 8090: the Conduit is 8000, the workspace 8080, the identity-provider tests 8081 and 8082.
EXPOSE 8090

# The health route answers with no session and no call to Valkey or the Conduit.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:8090/healthz').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]

CMD ["node", "apps/pages/dist/server/main.js"]
