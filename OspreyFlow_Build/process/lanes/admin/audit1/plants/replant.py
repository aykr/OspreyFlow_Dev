"""Audit 1 plants: each a violation in the shape the code has, run against its test, then restored."""
import os, subprocess, sys, tempfile
CORE = "/Users/ayankar/dev/osprey-wt/admin/OspreyFlow_Core"
TEST = "../OspreyFlow_Build/tests/services/api/test_owner_on_entra.py"
AUTH = "../OspreyFlow_Build/tests/services/api/test_auth_entra_claims.py"
PA, SCH = "packages/principal_auth/__init__.py", "services/api/scheduler.py"
PLANTS = [
 ("no_24_hour_rule", PA, "            or (now or datetime.now(UTC)) - read_at > ACCESS_FRESH\n", "", "24_hours"),
 ("never_signed_in_admitted", PA, "            read_at is None\n            or stored.clearance is None\n            or stored.org_unit is None\n            or (now", "            False\n            or (now", "never_read"),
 ("disabled_admitted", PA, "        if stored.disabled:\n            raise PrincipalRevoked", "        if False:\n            raise PrincipalRevoked", "disabled"),
 ("not_held_admitted_as_stale", PA, "        if stored is None:\n            raise PrincipalExchangeRefused(f\"owner {owner_id!r} is not a person of this deployment\")", "        if stored is None:\n            raise PrincipalAccessOutOfDate(owner_id, None)", "not_held"),
 ("store_failure_as_out_of_date", PA, "        except Exception as exc:  # noqa: BLE001 - every failure of the read is the store unread\n            raise OwnerRecordUnavailable(", "        except Exception as exc:  # noqa: BLE001 - every failure of the read is the store unread\n            raise PrincipalAccessOutOfDate(owner_id, None) from exc\n            raise OwnerRecordUnavailable(", "store_unread"),
 ("store_read_unbounded", PA, "                self._role_source.owner(mapping.tenant_id, owner_id),\n                timeout=self._role_lookup_timeout,", "                self._role_source.owner(mapping.tenant_id, owner_id),\n                timeout=None,", "store_unread"),
 ("schedule_out_of_date_as_unreachable", SCH, "        except PrincipalAccessOutOfDate as error:", "        except ZeroDivisionError as error:", "schedule_s_owner_out_of_date"),
 ("schedule_out_of_date_pauses", SCH, "                kind=\"owner_out_of_date\",\n                about_the_owner=False,", "                kind=\"owner_out_of_date\",\n                about_the_owner=True,", "schedule_s_owner_out_of_date"),
 ("store_unread_as_identity_provider", SCH, "        except OwnerRecordUnavailable as error:", "        except ZeroDivisionError as error:", "people_store_unread"),
 ("rule_out_of_date_as_unreachable", "services/api/rule_schedule.py", "        except PrincipalAccessOutOfDate as error:", "        except ZeroDivisionError as error:", "scheduled_rule"),
 ("list_out_of_date_generic", "services/api/list_schedule.py", "        except PrincipalAccessOutOfDate:", "        except ZeroDivisionError:", "list_refresh"),
 ("watch_out_of_date_as_unreachable", "services/api/monitor_schedule.py", "            if isinstance(error, PrincipalAccessOutOfDate):", "            if False:", "watch_s_owner"),
 ("kyc_deployer_words_generic", "services/api/kyc_sweep.py", "                        why = f\"its deployer, {rule.owner_id}, {ACCESS_OUT_OF_DATE_WORDS}\"\n", "", "kyc_check"),
 ("entra_owner_exchanged", PA, "        if self._claim_mapping.is_entra:\n            return await self._stored_owner(owner_id)\n", "", "AUTH:read_from_the_store_never_exchanged"),
 ("stored_owner_unit_from_nowhere", PA, "        principal_id, clearance, org_unit = oid, stored.clearance, stored.org_unit\n", "        principal_id, clearance, org_unit = oid, stored.clearance, \"unit-1\"\n", "acted_as_with_their_stored_access"),
 ("notice_says_sign_in_did_not_answer", "services/api/schedule_notices.py", "        \"did not run: its owner has not signed in to OspreyFlow within the last 24 hours. It runs \"\n        \"again once they sign in.\"\n", "        \"could not run: the sign-in service did not answer.\"\n", "notice"),
]
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for name, path, old, new, k in PLANTS:
    full = os.path.join(CORE, path); src = open(full).read()
    with open(os.path.join(out, f"plant_{name}.txt"), "w") as rec:
        if src.count(old) != 1:
            rec.write(f"PLANT MISS {name}\n"); print("MISS", name); continue
        open(full, "w").write(src.replace(old, new))
        try:
            env = dict(os.environ, PYTHONPYCACHEPREFIX=tempfile.mkdtemp())
            test, kk = (AUTH, k[5:]) if k.startswith("AUTH:") else (TEST, k)
            r = subprocess.run(["/private/tmp/claude-502/-Users-ayankar-dev-osprey-wt-admin/f9384bcf-e6a2-4167-b976-aa8c032154c3/scratchpad/t.sh", "-c", "../OspreyFlow_Build/pytest.ini", "-m", "not live", test, "-k", kk],
                               cwd=CORE, env=env, capture_output=True, text=True)
        finally:
            open(full, "w").write(src)
        lines = [l for l in r.stdout.splitlines() if l.startswith(("FAILED", "E   ")) or " passed" in l or " failed" in l]
        rec.write(f"# plant: {name} ({path}); fresh PYTHONPYCACHEPREFIX; -k {k}\n" + "\n".join(lines[-8:]) + "\n")
        print(name, "RED" if r.returncode != 0 else "GREEN(!)", lines[-1] if lines else "")
