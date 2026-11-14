"""Audit 4b's plants (ADR-148 Amendment 17): each one violation, run alone against its test with a fresh
PYTHONPYCACHEPREFIX on closed ports, then restored. `python3 replant.py`; a plant whose text is not found, or whose -k
selects nothing (exit 5), is a MISS, not red. The store's live plants run under a lease, recorded beside these."""
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[3]
CORE = BUILD.parent / "OspreyFlow_Core"
PA, APP = "packages/principal_auth/__init__.py", "services/api/app.py"
GUESTS = "../OspreyFlow_Build/tests/services/api/test_entra_guests.py"
PEOPLE = "../OspreyFlow_Build/tests/services/api/test_entra_people.py"
PLANTS = [
    ("guests_always_admitted", PA, "        if verified.guest and not await self._guests_admitted():", "        if False:", GUESTS, "refused_in_true_words or already_recorded"),
    ("guest_flag_never_set", PA, "        guest=bool(mapping.is_entra and guest),", "        guest=False,", GUESTS, "guest"),
    ("acct_not_a_guest", PA, "        guest = claims.get(\"acct\") in (1, \"1\") or guest_idp", "        guest = guest_idp", GUESTS, "refused_in_true_words"),
    ("setting_unread_admits", PA, "        return admitted is True", "        return True", GUESTS, "cannot_be_read or refused_in_true_words"),
    ("setting_read_unbounded", PA, "                self._role_source.guests_admitted(self._claim_mapping.tenant_id),\n                timeout=self._role_lookup_timeout,", "                self._role_source.guests_admitted(self._claim_mapping.tenant_id),\n                timeout=None,", GUESTS, "cannot_be_read or too_slow"),
    ("setting_failure_admits", PA, "        except Exception as exc:  # noqa: BLE001 - every failure of the read is the one refusal\n            raise unread(", "        except Exception as exc:  # noqa: BLE001 - every failure of the read is the one refusal\n            return True\n            raise unread(", GUESTS, "cannot_be_read or too_slow"),
    ("guest_seen_not_recorded_as_one", PA, "            guest=verified.guest,\n        )", "            guest=False,\n        )", GUESTS, "same_claims"),
    ("guest_owner_acted_as", PA, "        if stored.guest and not await self._guests_admitted(unread=OwnerRecordUnavailable):", "        if False:", GUESTS, "guest_owner"),
    ("route_behind_no_right", APP, "@app.put(\n    \"/v1/admin/sign-in/guests\", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))]\n)", "@app.put(\n    \"/v1/admin/sign-in/guests\"\n)", PEOPLE, "refused_without_manage_people"),
    ("change_not_audited", APP, "    await audit.record(principal=principal, action=\"set_guest_sign_in\",", "    if False: await audit.record(principal=principal, action=\"set_guest_sign_in\",", PEOPLE, "audited_with_before"),
    ("lockout_unchecked", APP, "        if not body.admitted:\n            try:", "        if False:\n            try:", PEOPLE, "every_people_manager_is_a_guest"),
    ("construction_admits_guests_unasked", PA, "        if verified.guest and not guest_admitted:", "        if False:", GUESTS, "construction_path"),
    ("guest_owner_unread_as_lookup", PA, "        if stored.guest and not await self._guests_admitted(unread=OwnerRecordUnavailable):", "        if stored.guest and not await self._guests_admitted():", GUESTS, "guest_owner_whose_setting"),
    ("superset_routes_dropped_for_guests", PA, "            routes = sorted(SUPERSET_ROUTES)", "            routes = None", GUESTS, "superset"),
    ("lockout_counts_guests", APP, "                    [p for p in await admin.list_people() if not p.guest], current", "                    await admin.list_people(), current", PEOPLE, "every_people_manager_is_a_guest"),
]
CLOSED = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
          "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | CLOSED
for name, path, old, new, test, k in PLANTS:
    f = CORE / path
    src = f.read_text(encoding="utf-8")
    record = HERE / f"plant_{name}.txt"
    if src.count(old) != 1:
        record.write_text(f"PLANT MISS {name}\n"); print("MISS", name); continue
    f.write_text(src.replace(old, new), encoding="utf-8")
    try:
        r = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c",
                            "../OspreyFlow_Build/pytest.ini", "-m", "not live", test, "-k", k],
                           cwd=CORE, env=env | {"PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}, capture_output=True,
                           text=True, timeout=300)
    finally:
        f.write_text(src, encoding="utf-8")
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "E   ")) or " passed" in ln or " failed" in ln]
    state = {0: "GREEN (not caught)", 5: "MISS (nothing selected)"}.get(r.returncode, "RED")
    record.write_text(f"# plant: {name} ({path}); fresh PYTHONPYCACHEPREFIX; closed ports; -k {k}\n# {state}\n" + "\n".join(lines[-6:]) + "\n")
    print(name, state, lines[-1] if lines else "")
