# ruff: noqa: E501
"""The check before Add (ADR-135 Amendment 14 point 2, the owner's first slice): one plant per thing the
check does, at its call site, run red against `tests/services/api/test_model_engine_checks.py`, then the
file put back from the text saved before the plant (never from git). Run from the worktree root after a
commit, offline on closed ports, with OspreyFlow_Core's own venv."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
ADMIN = CORE / "services/api/model_admin.py"
APP = CORE / "services/api/app.py"
TEST = "../OspreyFlow_Build/tests/services/api/test_model_engine_checks.py"
PLANTS = [
    ("Add without a passed check goes ahead", ADMIN,
     '            if pending is None:\n                raise ModelAdminRefused(\n                    "There is no check of that name. Check the key first',
     '            if False:\n                raise ModelAdminRefused(\n                    "There is no check of that name. Check the key first',
     "refused_without_a_passed_check"),
    ("a refused check keeps its key in the gateway", ADMIN,
     "            if not models or not all(m.ok for m in models):\n                if not provider.keyless:\n                    await self._gateway.delete_credential(provider.name)\n",
     "            if not models or not all(m.ok for m in models):\n                pass\n",
     "leaves_nothing_in_the_gateway"),
    ("a check lives for ever", ADMIN,
     "CHECK_LIFE = timedelta(minutes=15)\n", "CHECK_LIFE = timedelta(days=365)\n",
     "not_added_in_15_minutes"),
    ("a checked model's entry is left in the gateway", ADMIN,
     "                    finally:\n                        await self._gateway.delete_entry(entry_id(provider.name, model))\n",
     "                    finally:\n                        pass\n",
     "offers_nothing_until_add"),
    ("a refused body is echoed back", APP,
     '            status_code=422, detail={"error": "check_refused", "detail": _CHECK_BODY_REFUSED}\n',
     '            status_code=422, detail={"error": "check_refused", "detail": raw.decode()}\n',
     "appears_nowhere"),
    ("a key pasted into the label is taken", ADMIN,
     "                if shown and label_looks_like_a_key(shown):\n",
     "                if False:\n", "appears_nowhere"),
    ("Cancel leaves the key in the gateway", ADMIN,
     "            if not pending.provider.keyless:\n                await self._gateway.delete_credential(pending.provider.name)\n            rest =",
     "            rest =", "cancel_removes"),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env.pop("OSPREY_LANE", None)
red = 0
for i, (what, path, old, new, k) in enumerate(PLANTS, 1):
    saved = path.read_text(encoding="utf-8")
    assert saved.count(old) == 1, what
    path.write_text(saved.replace(old, new), encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "-k", k],
                              check=False, cwd=CORE, env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "failed" in last else "GREEN (the plant was not caught)"
        red += state == "RED"
        print(f"plant {i}: {what}\n  -k '{k}': {state} ({last})")
    finally:
        path.write_text(saved, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
raise SystemExit(0 if red == len(PLANTS) else 1)
