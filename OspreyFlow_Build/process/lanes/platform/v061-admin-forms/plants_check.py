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
    # The shape a real bypass takes: a check whose model was refused still held for Add (the lane
    # review of 506ad53, item 8: the first version of this plant crashed instead).
    (
        "Add after a refused check goes ahead",
        ADMIN,
        "            if not models or not all(m.ok for m in models):\n",
        "            if not models:\n",
        "refused_without_a_passed_check",
    ),
    (
        "a refused check keeps its key in the gateway",
        ADMIN,
        "            if not models or not all(m.ok for m in models):\n                if not provider.keyless:\n                    await self._gateway.delete_credential(provider.name)\n",
        "            if not models or not all(m.ok for m in models):\n                pass\n",
        "leaves_nothing_in_the_gateway",
    ),
    (
        "a check lives for ever",
        ADMIN,
        "CHECK_LIFE = timedelta(minutes=15)\n",
        "CHECK_LIFE = timedelta(days=365)\n",
        "not_added_in_15_minutes",
    ),
    (
        "a checked model's entry is left in the gateway",
        ADMIN,
        "            finally:\n                await self._gateway.delete_entry(entry_id(named, model))\n",
        "            finally:\n                pass\n",
        "offers_nothing_until_add",
    ),
    # Where a refused body is answered since the review's fixes (`_check_refusal`): not JSON at all,
    # then a field's rule quoting what it refused.
    ("a refused body is echoed back", APP,
     '        return {"error": "check_refused", "detail": _CHECK_BODY_REFUSED}\n    errors =',
     '        return {"error": "check_refused", "detail": raw.decode()}\n    errors =',
     "appears_nowhere"),
    ("a refused field's words not redacted", APP,
     '"words": model_admin_module.redacted(msg, sent)}', '"words": msg}',
     "refused_field_is_named"),
    ("a key pasted into the label is taken", ADMIN,
     "                if shown and label_looks_like_a_key(shown):\n",
     "                if False:\n", "appears_nowhere"),
    ("Cancel leaves the key in the gateway", ADMIN,
     "            if not pending.provider.keyless:\n                await self._gateway.delete_credential(pending.provider.name)\n            rest =",
     "            rest =", "cancel_removes"),
    # The lane review of 506ad53's fixes.
    (
        "a lapsed check's key kept until someone asks (no sweep at start)",
        ADMIN,
        "        self._sweeping = asyncio.create_task(self._keep_sweeping())\n",
        "",
        "sweep_runs_by_itself",
    ),
    # The owner's ruling 18 (replacing "the old add route takes a name being checked": that route is
    # gone): an add route beside the check's, in the shape P1's had.
    (
        "an add route beside the check's",
        APP,
        '@app.put("/v1/admin/models/engines/{name}", dependencies=_MANAGE_MODELS)\n',
        '@app.post("/v1/admin/models/engines", dependencies=_MANAGE_MODELS)\nasync def models_admin_add_engine_route(\n    request: Request, principal: PrincipalDep, admin: ModelAdminDep\n) -> ModelsAdminView:\n    body = await _model_admin_body(request, EngineInput)\n    await admin.edit_engine(principal.id, body.provider.name, body.provider)\n    return admin.view()\n\n\n@app.put("/v1/admin/models/engines/{name}", dependencies=_MANAGE_MODELS)\n',
        "no_route_adds",
    ),
    (
        "a key pasted into a model name is checked",
        ADMIN,
        "    if any(model_looks_like_a_key(m) for m in provider.roles.values()):\n",
        "    if False:\n",
        "pasted_into_a_model_name",
    ),
    (
        "the key recorded as set by whoever pressed Add",
        ADMIN,
        "KeyRecord(set_at=pending.at, set_by=pending.by)",
        "KeyRecord(set_at=self._now(), set_by=by)",
        "recorded_as_set_by",
    ),
    (
        "a refused job not named, only the roles",
        APP,
        '        if field == "provider.roles" and (job := re.match(r"the (\\w+) model ", msg)):\n',
        "        if False and (job := None):\n",
        "refused_field_is_named",
    ),
    (
        "the key handed to the gateway before the render's refusal",
        ADMIN,
        'deep=True), sent)  # fmt: skip\n            self._made_by_the_render(provider)\n            if provider.keyless and key is not None:\n                raise ModelAdminRefused(\n                    f"{provider.name} signs in by the gateway\'s own IAM role, so no key is kept "\n                    "for it; send none."',
        'deep=True), sent)  # fmt: skip\n            if not provider.keyless and key is not None:\n                await self._gateway.put_credential(provider.name, key)\n            self._made_by_the_render(provider)\n            if provider.keyless and key is not None:\n                raise ModelAdminRefused(\n                    f"{provider.name} signs in by the gateway\'s own IAM role, so no key is kept "\n                    "for it; send none."',
        "render_did_not_make",
        "../OspreyFlow_Build/tests/services/api/test_model_engine_kinds.py",
    ),
    # The owner's ruling 19: an edit and a new key checked too.
    (
        "an edited model saved unchecked",
        ADMIN,
        '            if models:\n                await self._checked(provider, key, models, kept="its models, address and key")\n',
        "",
        "edited_model_name_is_checked",
    ),
    (
        "a moved address saved without its key",
        ADMIN,
        "            if moved and not provider.keyless and key is None:\n",
        "            if False:\n",
        "changed_address_takes_its_key",
    ),
    (
        "a new key replaces the held one unchecked",
        ADMIN,
        '            if action != "key_moved":\n',
        "            if False:\n",
        "new_key_is_checked_before",
    ),
    (
        "an edit's check leaves its key in the gateway",
        ADMIN,
        "            if own:\n                await self._gateway.delete_credential(probe)\n",
        "            if own:\n                pass\n",
        "new_key_is_checked_before",
    ),
    (
        "a key pasted into the label taken on an edit",
        ADMIN,
        '            _no_key_shown(provider, "nothing was changed")\n',
        "",
        "through_an_edit",
    ),
    # Found building ruling 19: the gateway cools a refused entry's name down for a minute.
    (
        "each check under the engine's own name",
        ADMIN,
        '    return f"{probe_name(provider)}-{secrets.token_hex(4)}"\n',
        "    return provider\n",
        "corrected_key",
    ),
    (
        "a check's key left unrecorded when its save fails",
        ADMIN,
        "            except BaseException:\n                # Unrecorded, nothing would ever remove it: the key goes with the refusal.\n                if not provider.keyless:\n                    await self._gateway.delete_credential(provider.name)\n                raise\n",
        "            except BaseException:\n                raise\n",
        "cannot_be_written",
        "../OspreyFlow_Build/tests/services/api/test_model_admin_routes.py",
    ),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994", "MINIO_ENDPOINT": "localhost:59995",
       "OPENSEARCH_PORT": "59999"}
env.pop("OSPREY_LANE", None)
red = 0
for i, (what, path, old, new, k, *other) in enumerate(PLANTS, 1):
    saved = path.read_text(encoding="utf-8")
    assert saved.count(old) == 1, what
    path.write_text(saved.replace(old, new), encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", other[0] if other else TEST, "-k", k],
                              check=False, cwd=CORE, env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = (
            "RED"
            if done.returncode != 0 and "failed" in last
            else "GREEN (the plant was not caught)"
        )
        red += state == "RED"
        print(f"plant {i}: {what}\n  -k '{k}': {state} ({last})")
    finally:
        path.write_text(saved, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
raise SystemExit(0 if red == len(PLANTS) else 1)
