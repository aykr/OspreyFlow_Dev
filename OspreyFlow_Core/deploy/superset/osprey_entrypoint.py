"""Superset's start for OspreyFlow (`06_DECISIONS.md` ADR-111 Amendment 2): make the metadata
database if it is missing, migrate it, register the reporting mart as Superset's one data source
(read through the read-only login), then serve. Idempotent: every restart repeats it harmlessly."""

import os
import subprocess
import sys

import psycopg2

host, port = os.environ.get("POSTGRES_HOST", "postgres"), int(os.environ.get("POSTGRES_PORT", "5432"))
user, password = os.environ["POSTGRES_USER"], os.environ["POSTGRES_PASSWORD"]
metadata = os.environ.get("SUPERSET_METADATA_DB", "superset")

conn = psycopg2.connect(user=user, host=host, port=port, password=password, dbname=os.environ.get("POSTGRES_DB", "ospreyflow"))
conn.autocommit = True  # CREATE DATABASE cannot run inside a transaction
with conn.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (metadata,))
    if cur.fetchone() is None:
        cur.execute(f'CREATE DATABASE "{metadata}"')
conn.close()


def superset(*args: str) -> None:
    subprocess.run(["superset", *args], check=True)


superset("db", "upgrade")
superset("init")
reader, reader_password = os.environ.get("REPORT_MART_READER", "osprey_reports_reader"), os.environ["REPORT_MART_READER_PASSWORD"]
mart = f"postgresql+psycopg2://{reader}:{reader_password}@{host}:{port}/{os.environ.get('POSTGRES_DB', 'ospreyflow')}"
superset("set-database-uri", "--database_name", "OspreyFlow reports", "--uri", mart)

sys.stdout.flush()
os.execvp("gunicorn", ["gunicorn", "--workers", "2", "--worker-class", "gthread", "--threads", "4",
                       "--timeout", "120", "--bind", "0.0.0.0:8088", "superset.app:create_app()"])
