# The reference dashboard (`06_DECISIONS.md` ADR-111 decision 9, Amendment 2): Apache Superset
# (Apache-2.0), pinned by digest, a container of its own outside the three tiers. It reads only the
# reporting mart, through a read-only login, and signs people in through the deployment's identity
# provider. Two drivers the official image lacks, both BSD-licensed: pg8000 (not psycopg2, LGPL) and
# Authlib for the sign-in.
FROM apache/superset@sha256:15e110b8533d3cb6a0d529512ea71252b0ac62e3f72b1f7a5000f1361822ac26
USER root
RUN pip install --no-cache-dir pg8000==1.31.2 authlib==1.3.2
COPY superset_config.py /app/pythonpath/superset_config.py
COPY osprey_entrypoint.py /app/osprey_entrypoint.py
USER superset
EXPOSE 8088
ENTRYPOINT ["python", "/app/osprey_entrypoint.py"]
