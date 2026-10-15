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
# them (cryptography, msgpack, pyarrow, pyOpenSSL) wait for Superset (`.trivyignore`).
RUN uv pip install --no-cache --python /app/.venv/bin/python psycopg2-binary==2.9.6 \
    authlib==1.6.9 mako==1.3.12 pyjwt==2.14.0 pillow==12.3.0 urllib3==2.8.0 pyasn1==0.6.4 \
    jaraco.context==6.1.0 wheel==0.46.2 setuptools==84.0.0
# setuptools bundles its own jaraco.context and wheel; the system Python's copy is brought up too.
RUN /usr/local/bin/python -m pip install --no-cache-dir --upgrade setuptools==84.0.0
COPY superset_config.py osprey_theme.json /app/pythonpath/
# The OspreyFlow mark and favicon, served by Superset itself (APP_ICON, FAVICONS).
COPY brand/osprey-mark.svg brand/osprey-favicon.svg /app/superset/static/assets/images/
# Superset's loading animation, replaced by the OspreyFlow mark (brand/make_loader.py). The hashed
# name belongs to the pinned image above: re-check it whenever the digest changes.
COPY brand/loading.gif /app/superset/static/assets/loading.cff8a5da.gif
COPY brand/loading.gif /app/superset/static/assets/images/loading.gif
COPY osprey_entrypoint.py /app/osprey_entrypoint.py
COPY osprey_setup.py osprey_palette.py /app/
USER superset
EXPOSE 8088
ENTRYPOINT ["python", "/app/osprey_entrypoint.py"]
