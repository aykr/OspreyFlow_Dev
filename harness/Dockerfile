# harness/Dockerfile — the harness's own bootstrap image, `docs/05_DEPLOYMENT.md` §2's own worked
# example: "One bootstrap command starts it... `ghcr.io/ospreyflow/harness:latest`."
#
# **Minimal by file tree, not by dependency set** — the same shape `services/api/Dockerfile` and
# `services/ingest/Dockerfile` already use: `uv sync` installs this project's one, full dependency
# set (a single source of truth, not a second hand-pruned manifest to drift from it), and only the
# source directories this image's own entrypoint actually reaches are copied in. Checked directly,
# not assumed: tracing every module `harness.render`, `harness.apply`, `harness.backup`,
# `harness.restore`, `harness.preflight.__main__`, `harness.webapp` (`Stage 2 §6` part A) and
# `scripts.osprey_bundle` import, recursively, touches exactly three project-tree roots —
# `harness`, `packages/schemas`, `scripts` — and nothing under `services/` or any other
# `packages/*` subdirectory. `harness/webapp_auth.py`'s own module docstring has the reason
# `services/api/auth.py`'s existing JWT verification is not reused: it lives outside this set.
#
# **Now also the browser setup harness's own server, `Stage 2 §6` part A — the "future no-
# subcommand mode" this comment used to name as not built yet.** `harness/__main__.py`'s own
# subcommand dispatch (`render`, `preflight`, `apply`, `backup`, `restore`, `bundle`) still runs a
# single command and exits; no subcommand instead starts `harness.webapp`, a long-lived process
# for the setup screens and, later, the post-launch admin console (`docs/05_DEPLOYMENT.md` §2.5).
# The docker-socket privilege §2.5 describes is still runtime-scoped, not baked in here — see the
# `ENTRYPOINT` comment below for what does and does not change between the two modes.
#
# **The privilege drop (amendment 22, part B) is two container invocations of this one image, not
# a flag inside it.** `harness.webapp.create_app`'s own `mode` parameter (`--mode setup|console`)
# is an *application*-level boundary — which routes exist — and cannot express or enforce a
# *container*-level property: whether `/var/run/docker.sock` is mounted, or whether the root
# filesystem is writable, are both facts about the `docker run` invocation, not about the process
# running inside it. So: the same image, the same non-root `osprey` user (already true for either
# mode, below), run once *with* the socket mount for setup mode (Launch needs `docker compose`) and
# once *without* it, plus `--read-only` (and a `--tmpfs /tmp` for Python's own bytecode cache), for
# console mode after Launch has handed off. Never faked with an in-image flag pretending the socket
# or the writable root are gone when the container was actually started with them.
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv==0.5.14

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY harness ./harness
COPY packages/schemas ./packages/schemas
COPY scripts ./scripts

# The Docker CLI itself, taken from Docker's own official `cli` image rather than Debian's package
# archive — this image only ever shells out to `docker`/`docker compose` (`harness/apply.py`'s own
# `_compose`, `_run`), it never runs a daemon of its own, and the socket mounted at run time (below)
# is nothing to talk to without a client on this side of it. **Found, not assumed:** Debian trixie's
# archive has neither `docker-compose-v2` nor `docker-compose-plugin` under those names — the
# official image is the one place both the client and the `compose` plugin are guaranteed to match.
FROM docker:27-cli AS dockercli

# `apps/harness`'s own build — `Stage 2 §6` part A, ruling R1: "the same React/Vite/TypeScript
# toolchain and design tokens as apps/workspace", served by `harness.webapp` inside this image
# (ruling R1's own "no second image"), not from a separate static-file image the way
# `apps/workspace/Dockerfile` builds one. That is also why `apps/harness` is recorded as a
# `Kind.LIBRARY` in `harness/service_inventory.py`, not `Kind.DEPLOYABLE` — its built output ships
# inside this image rather than running as its own process.
FROM node:22-slim AS frontend-builder

WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/harness/package.json apps/harness/package.json
COPY apps/workspace/package.json apps/workspace/package.json
RUN npm ci
COPY apps/harness ./apps/harness
# Only the two design-token sources this app's own CSS imports reach (`apps/harness/src/main.tsx`,
# `apps/harness/keyboard/setup-harness.tsx`) — not the whole of `apps/workspace`, which this build
# does not need and should not pull into this image's own build context.
COPY docs/design ./docs/design
COPY apps/workspace/src/design ./apps/workspace/src/design
RUN npm run build --workspace apps/harness

FROM python:3.12-slim

# Base-image OS packages lag the upstream image's own last-published point release; picking up
# current Debian security patches at build time is what keeps `trivy image` (below) a real gate.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose \
    /usr/local/libexec/docker/cli-plugins/docker-compose

RUN useradd --create-home --uid 10001 osprey
WORKDIR /app

# `--chown` is not cosmetic — `services/ingest/Dockerfile`'s own comment names the exact failure:
# `COPY` preserves the source file's mode, and a single restrictively-permissioned file anywhere in
# the copied tree lands in the image owned by root and unreadable by `osprey`, dying on import with
# a `PermissionError` naming a file nobody thought to check. Applied here from that finding, not
# rediscovered.
COPY --from=builder --chown=osprey:osprey /app/.venv ./.venv
COPY --from=builder --chown=osprey:osprey /app/harness ./harness
COPY --from=builder --chown=osprey:osprey /app/packages ./packages
COPY --from=builder --chown=osprey:osprey /app/scripts ./scripts
# `harness/webapp.py`'s own `FRONTEND_DIST` — `apps/harness/dist` relative to this image's own
# `/app` root, the same path a bare checkout's `npx vite build` produces, so `create_app` needs no
# image-specific branch to find it.
COPY --from=frontend-builder --chown=osprey:osprey /app/apps/harness/dist ./apps/harness/dist

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app:/app/packages" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME="/app"
# `PYTHONDONTWRITEBYTECODE`: console mode's own `--read-only` (see the two-invocation comment
# above) makes `/app` unwritable, and every module here is copied in as plain `.py` source, not
# precompiled — without this, Python's first import of each one under a read-only root would
# attempt (and fail) to cache its own `.pyc`. CPython tolerates that failure rather than crashing,
# but there is no reason to let it try at all.

# The docker socket mounted at run time (`-v /var/run/docker.sock:/var/run/docker.sock`, this
# image's own one documented privilege — see `ENTRYPOINT` below) is commonly group-owned on a
# Linux host, and membership in that group is what lets `osprey` use a mounted socket without the
# socket itself needing to be world-writable or this process needing to run as root. **Disclosed
# limit, not solved here:** the host's own docker group GID is not knowable at image-build time: an
# operator whose host GID does not match this image's `docker` group re-creates it with the host's
# own GID (`--group-add`, or `docker run --user root` for a one-off) — the same accommodation every
# "docker outside of docker" image needs, not one specific to this image. Docker Desktop's own
# socket (macOS, Windows) is typically reachable without this at all, since its proxy does not
# enforce host-side Unix group ownership the way a native Linux daemon's socket does.
RUN groupadd docker && usermod -aG docker osprey

USER osprey

# **The one privilege this image needs, and only while running** (`docs/05_DEPLOYMENT.md` §2.5).
# `-v /var/run/docker.sock:/var/run/docker.sock` is not baked in here — it cannot be, a `Dockerfile`
# has no way to declare a bind mount — so it is declared in the one place that is true: at
# `docker run` time, in `05_DEPLOYMENT.md` §2's own worked example, and nowhere does this image
# hold that socket, or any other elevated privilege, beyond what that run command grants.
#
# **No `HEALTHCHECK` here — correct for the subcommand modes, a disclosed gap for the no-
# subcommand one.** Every subcommand (`render`, `preflight`, `apply`, `backup`, `restore`,
# `bundle`) still runs once and exits, the same "no long-running health to report" shape
# `services/ingest/Dockerfile` already has none for. No subcommand (`Stage 2 §6` part A) now runs
# `harness.webapp` indefinitely instead, which does have a real liveness endpoint to check
# (`GET /api/config`) — a `HEALTHCHECK` for that mode alone is real, undone work, left to whichever
# part actually wires this image into a deployment's own health-checked stack.
ENTRYPOINT ["python", "-m", "harness"]
