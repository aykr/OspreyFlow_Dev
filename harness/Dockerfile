# harness/Dockerfile — the harness's own bootstrap image, `docs/05_DEPLOYMENT.md` §2's own worked
# example: "One bootstrap command starts it... `ghcr.io/ospreyflow/harness:latest`."
#
# **Minimal by file tree, not by dependency set** — the same shape `services/api/Dockerfile` and
# `services/ingest/Dockerfile` already use: `uv sync` installs this project's one, full dependency
# set (a single source of truth, not a second hand-pruned manifest to drift from it), and only the
# source directories this image's own entrypoint actually reaches are copied in. Checked directly,
# not assumed: tracing every module `harness.render`, `harness.apply`, `harness.backup`,
# `harness.restore`, `harness.preflight.__main__` and `scripts.osprey_bundle` import, recursively,
# touches exactly three project-tree roots — `harness`, `packages/schemas`, `scripts` — and nothing
# under `services/` or any other `packages/*` subdirectory.
#
# **Not a long-running server** (`docs/05_DEPLOYMENT.md` §2.5: "It does not run as a privileged
# long-lived service. During setup it needs the container socket; the admin console it becomes
# afterwards does not."). `harness/__main__.py`'s own subcommand dispatch (`render`, `preflight`,
# `apply`, `backup`, `restore`, `bundle`) is what a real deployment or the setup harness invokes
# today; `Stage 2 §6`'s own browser screens are the same image's future no-subcommand mode, not
# built yet — `harness/__main__.py`'s own module docstring says so.
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

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app:/app/packages" \
    PYTHONUNBUFFERED=1 \
    HOME="/app"

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
# hold that socket, or any other elevated privilege, once the one command it was run for exits.
# There is no `HEALTHCHECK` here for the same reason `services/ingest/Dockerfile` has none: a CLI
# that runs one command and exits has no long-running health to report.
ENTRYPOINT ["python", "-m", "harness"]
