# OspreyFlow's own model gateway (ADR-135; the owner's ruling of 21 November 2026): LiteLLM 1.101.0
# built from the MIT-licensed files PyPI publishes, in a fresh image of ours, without the
# publisher's commercially licensed folder or its proprietary package. It is never derived from the
# publisher's image: a later `rm` over that image would hide the folder and leave its layers in what
# is shipped. Built from this folder alone (`docker build deploy/litellm`); NOTICE says where each
# part came from.
#
# What keeps the commercial parts out, in the order the build meets them:
#  1. the install names `litellm` and `litellm-proxy-extras` and holds every other package to the
#     versions of `constraints.txt`, made from the pinned publisher image's own venv;
#  2. `overrides.txt` removes the one proprietary package the `proxy` extra would bring in;
#  3. `licence_gate.py` reads what is installed, fails the build on that package, on any
#     distribution declaring a proprietary licence and on the commercial folder, in the builder and
#     again over what the final stage was given, and is deleted afterwards;
#  4. the final stage copies from the builder only the five paths named below.
# The test that holds this file to all of that is `tests/harness/test_own_gateway_image.py`.
FROM ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a AS uvbin

# Builder: compilers and the Prisma command line's npm, none of which ship.
FROM cgr.dev/chainguard/wolfi-base@sha256:e624c5d5e42382ce7165ddafcbbf8e6769a24cbd02ea6114b880b05ae5ba2a8d AS builder
USER root
WORKDIR /app
# The base image configures only Chainguard's authenticated repository; the public Wolfi one is
# added so `apk add` works (the publisher's own Dockerfile does the same).
RUN echo "https://packages.wolfi.dev/os" >> /etc/apk/repositories
RUN apk add --no-cache bash gcc python-3.13 python-3.13-dev rust openssl openssl-dev nodejs npm libsndfile
COPY --from=uvbin /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 PATH="/app/.venv/bin:${PATH}"

COPY constraints.txt overrides.txt publisher-resolution.txt ./
# The extras are the pinned image's own (trimming them is a later, measured choice).
RUN uv venv /app/.venv --python python3.13 \
    && uv pip install --python /app/.venv/bin/python --constraint constraints.txt --override overrides.txt \
        --override publisher-resolution.txt \
        "litellm[proxy,proxy-runtime,extra_proxy,semantic-router,saml,bedrock-realtime]==1.101.0" \
        "litellm-proxy-extras==0.4.94"

# The gate, over what was just installed (it stops this build on the commercial package, or on any
# distribution declaring a proprietary licence).
COPY licence_gate.py /tmp/licence_gate.py
RUN python /tmp/licence_gate.py /app/.venv/lib/python3.13/site-packages

# The two entrypoint scripts, as the publisher's repository holds them (NOTICE), the schema and the
# migration script as the package carries them (byte for byte the repository's own at the pinned
# revision: the entrypoint runs the migration by its source path).
COPY docker/ /app/docker/
RUN sed -i 's/\r$//' /app/docker/entrypoint.sh /app/docker/prod_entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh /app/docker/prod_entrypoint.sh \
    && mkdir -p /app/litellm/proxy \
    && cp /app/.venv/lib/python3.13/site-packages/litellm/proxy/schema.prisma /app/schema.prisma \
    && cp /app/.venv/lib/python3.13/site-packages/litellm/proxy/prisma_migration.py \
        /app/litellm/proxy/prisma_migration.py

# The Prisma command line and its engines, fetched here (the one step that needs the network) and
# kept under /opt/prisma, a fixed path every uid can read (made so here, in the builder, so the final
# stage need not copy it again), so a first start needs none.
RUN HOME=/opt/prisma XDG_CACHE_HOME=/opt/prisma/.cache PRISMA_BINARY_CACHE_DIR=/opt/prisma/binaries \
    npm_config_cache=/root/.npm \
    prisma generate --schema=./schema.prisma \
    && chmod -R a+rX /opt/prisma

# Runtime: Wolfi again, with only what the gateway runs on.
FROM cgr.dev/chainguard/wolfi-base@sha256:e624c5d5e42382ce7165ddafcbbf8e6769a24cbd02ea6114b880b05ae5ba2a8d
USER root
RUN echo "https://packages.wolfi.dev/os" >> /etc/apk/repositories
# The distribution's fixes the pinned base does not carry yet, as every other image takes them. The
# day's stamp (`harness/upgrade_stamp.py`): every build passes today's date, so this layer is made
# again each day and a builder's cached copy cannot keep an old distribution's flaws.
# The base's package list (/etc/apk/world) holds each package at the exact version it was built with
# (`zlib=1.3.2-r5`), so `apk upgrade` alone moves none of them: the pins are taken off first (found
# by the first scan, 21 November 2026: zlib and the CA bundle stayed at versions with fixes out).
ARG OSPREY_UPGRADE_STAMP=
RUN echo "distribution fixes as of ${OSPREY_UPGRADE_STAMP:-an unstamped build}" \
    && sed -i -E 's/[=<>~].*$//' /etc/apk/world \
    && apk add --no-cache bash openssl tzdata nodejs python-3.13 libsndfile \
    && apk upgrade --no-cache

WORKDIR /app
ENV PATH="/app/.venv/bin:${PATH}" \
    PRISMA_BINARY_CACHE_DIR=/opt/prisma/binaries \
    PRISMA_CLI_PATH=/opt/prisma/binaries/node_modules/.bin/prisma \
    PRISMA_CLI_QUERY_ENGINE_TYPE=binary \
    PRISMA_OFFLINE_MODE=true \
    HOME=/home/litellm
LABEL org.opencontainers.image.title="OspreyFlow model gateway" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.description="LiteLLM 1.101.0 from PyPI's MIT files, without the publisher's commercially licensed folder or package"

# Only what the gateway runs on, and only from the builder's five paths: the venv, the entrypoint
# scripts, the schema, the migration script (run by its source path) and the Prisma command line
# and engines.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/docker /app/docker
COPY --from=builder /app/schema.prisma /app/schema.prisma
COPY --from=builder /app/litellm/proxy/prisma_migration.py /app/litellm/proxy/prisma_migration.py
COPY --from=builder /opt/prisma /opt/prisma

# The checks the publisher's image makes (tornado's test folder, with its test certificates, is
# removed as theirs is), and the gate again over what the stages handed over.
COPY licence_gate.py /tmp/licence_gate.py
RUN rm -rf /app/.venv/lib/python3.13/site-packages/tornado/test \
    && test -x /opt/prisma/binaries/node_modules/.bin/prisma \
    && test -f /opt/prisma/binaries/node_modules/prisma/build/index.js \
    && python -c "from prisma.client import BINARY_PATHS; paths = list(BINARY_PATHS.query_engine.values()); assert paths and all(p.startswith('/opt/prisma/') for p in paths), paths"
RUN python /tmp/licence_gate.py /app/.venv/lib/python3.13/site-packages --app /app && rm /tmp/licence_gate.py

# ADR-148 decision 3: the one numeric UID all our images run as.
RUN addgroup -g 10001 -S litellm && adduser -S -D -u 10001 -G litellm -h /home/litellm litellm
USER 10001:10001
EXPOSE 4000/tcp
ENTRYPOINT ["docker/prod_entrypoint.sh"]
CMD ["--port", "4000"]
