# The reference dashboard (`06_DECISIONS.md` ADR-111 decision 9, Amendment 2): Apache Superset
# (Apache-2.0), pinned by digest, a container of its own outside the three tiers. It reads only the
# reporting mart, through a read-only login, and signs people in through the deployment's identity
# provider. Two packages the official image lacks: psycopg2-binary, the Postgres driver Superset is
# built and tested against (LGPL-3.0, a recorded exception in `00_ARCHITECTURE.md` §7: an unmodified
# installed package in this container only), and Authlib (BSD-3) for the sign-in. pg8000 (BSD) was
# tried first and does not work with Superset: it types a string parameter as varchar, and Superset
# looks charts and dashboards up by the id in the URL as a string, so every edit and delete answered
# "Not found" (found live, 11 October 2026).
# Superset 6.1.0 (ADR-111 Amendment 4): themed from the tokens, light and dark.
FROM apache/superset@sha256:16b50bbef6648912a79e3293d418fefa743ce555d36c5af6b85d859119ed7f88
USER root
# The base image's Debian packages brought up to date at build (the release scan, 15 October 2026).
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
# 6.x keeps Superset in its own environment, managed by uv. Beyond the two it lacks, the packages the
# release scan found with a fix inside the ranges Superset 6.1.0 itself declares; the fixes outside
# them (cryptography, msgpack, pyarrow, pyOpenSSL, Pillow 13, and dnspython 2.9, which needs a newer
# Python than the image's 3.10) wait for Superset (`.trivyignore`). Brought up again for v0.4.0
# (ADR-111 Amendment 7): Authlib, brotli and certifi; and pyasn1 0.6.5 on 31 October 2026.
RUN uv pip install --no-cache --python /app/.venv/bin/python psycopg2-binary==2.9.6 \
    authlib==1.9.1 mako==1.3.12 pyjwt==2.14.0 pillow==12.3.0 urllib3==2.8.0 pyasn1==0.6.5 \
    jaraco.context==6.1.0 wheel==0.46.2 setuptools==84.0.0 brotli==1.2.1 certifi==2026.10.18
# setuptools bundles its own jaraco.context and wheel; the system Python's copy is brought up too,
# and so is the uv installed there (ADR-111 Amendment 7).
RUN /usr/local/bin/python -m pip install --no-cache-dir --upgrade setuptools==84.0.0 uv==0.13.4
COPY superset_config.py osprey_theme.json /app/pythonpath/
# The OspreyFlow mark and favicon, served by Superset itself (APP_ICON, FAVICONS).
COPY brand/osprey-mark.svg brand/osprey-favicon.svg /app/superset/static/assets/images/
# Superset's loading animation, replaced by the OspreyFlow mark (brand/make_loader.py). The hashed
# name belongs to the pinned image above: re-check it whenever the digest changes.
COPY brand/loading.gif /app/superset/static/assets/loading.cff8a5da.gif
COPY brand/loading.gif /app/superset/static/assets/images/loading.gif
COPY osprey_entrypoint.py /app/osprey_entrypoint.py
COPY osprey_setup.py osprey_palette.py /app/
# ADR-148 decision 3: the base image's `superset` user takes the one numeric UID all our images run
# as, and keeps everything it owned: what its old uid owned is given the new uid, and what its old
# group owned the new gid alone (a file of another owner in that group keeps its owner). Checked in
# the same step: the base's ids are an ordinary user's (never root's, whose files would all be handed
# over, nor already 10001), the new ids are 10001, and nothing keeps the old uid or the old gid.
RUN old_uid="$(id -u superset)" && old_gid="$(id -g superset)" \
    && test "$old_uid" -ge 1000 && test "$old_uid" != 10001 \
    && test "$old_gid" -ge 1000 && test "$old_gid" != 10001 \
    && usermod -u 10001 superset && groupmod -g 10001 superset \
    && find / -xdev -uid "$old_uid" -exec chown -h 10001 {} + \
    && find / -xdev -gid "$old_gid" -exec chgrp -h 10001 {} + \
    && test "$(id -u superset)" = 10001 && test "$(id -g superset)" = 10001 \
    && test -z "$(find / -xdev -uid "$old_uid" -print -quit)" \
    && test -z "$(find / -xdev -gid "$old_gid" -print -quit)"
USER 10001:10001
EXPOSE 8088
ENTRYPOINT ["python", "/app/osprey_entrypoint.py"]
