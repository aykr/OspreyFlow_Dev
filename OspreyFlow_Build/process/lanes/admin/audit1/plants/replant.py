"""Audit 1's offline plants (ADR-148 Amendment 16): each one violation, in the shape the code has, run alone against
its test with a fresh PYTHONPYCACHEPREFIX on closed ports, then restored. `python3 replant.py <out dir>` from anywhere
in the checkout; a plant whose text is not found, or whose `-k` selects nothing (pytest's exit 5), is a MISS, not red.
The live plants (the store's tenant guard, the pause count) run under a lease, recorded beside these."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
CORE = ROOT / "OspreyFlow_Core"
OWNER = "../OspreyFlow_Build/tests/services/api/test_owner_on_entra.py"
AUTH = "../OspreyFlow_Build/tests/services/api/test_auth_entra_claims.py"
PA, SCH = "packages/principal_auth/__init__.py", "services/api/scheduler.py"
#: Closed ports and no lane: an offline run never reaches a stack (the lease's rule).
CLOSED = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
          "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
PLANTS = [  # name, file, old, new, test, -k
    ("no_24_hour_rule", PA, "            or (now or datetime.now(UTC)) - read_at > ACCESS_FRESH\n", "", OWNER, "24_hours"),
    ("never_signed_in_admitted", PA, "            read_at is None\n            or stored.clearance is None\n            or stored.org_unit is None\n            or (now", "            False\n            or (now", OWNER, "never_read"),
    ("disabled_admitted", PA, "        if stored.disabled:\n            raise PrincipalRevoked", "        if False:\n            raise PrincipalRevoked", OWNER, "disabled"),
    ("not_held_admitted_as_stale", PA, "            raise OwnerNotHeld(f\"owner {owner_id!r} is not a person of this deployment\")", "            raise PrincipalAccessOutOfDate(owner_id, None)", OWNER, "not_held"),
    ("store_failure_as_out_of_date", PA, "        except Exception as exc:  # noqa: BLE001 - every failure of the read is the store unread\n            raise OwnerRecordUnavailable(", "        except Exception as exc:  # noqa: BLE001 - every failure of the read is the store unread\n            raise PrincipalAccessOutOfDate(owner_id, None) from exc\n            raise OwnerRecordUnavailable(", OWNER, "store_unread or another_tenant"),
    ("store_read_unbounded", PA, "                self._role_source.owner(mapping.tenant_id, owner_id),\n                timeout=self._role_lookup_timeout,", "                self._role_source.owner(mapping.tenant_id, owner_id),\n                timeout=None,", OWNER, "store_unread"),
    ("entra_owner_exchanged", PA, "        if self._claim_mapping.is_entra:\n            return await self._stored_owner(owner_id)\n", "", AUTH, "read_from_the_store_never_exchanged"),
    ("stored_owner_unit_from_nowhere", PA, "        principal_id, clearance, org_unit = oid, stored.clearance, stored.org_unit\n", "        principal_id, clearance, org_unit = oid, stored.clearance, \"unit-1\"\n", OWNER, "acted_as_with_their_stored_access"),
    ("schedule_out_of_date_as_unreachable", SCH, "        except PrincipalAccessOutOfDate as error:", "        except ZeroDivisionError as error:", OWNER, "schedule_s_owner_out_of_date"),
    ("schedule_out_of_date_flagged_about_the_owner", SCH, "                kind=\"owner_out_of_date\",\n                about_the_owner=False,", "                kind=\"owner_out_of_date\",\n                about_the_owner=True,", OWNER, "schedule_s_owner_out_of_date"),
    ("store_unread_as_identity_provider", SCH, "        except OwnerRecordUnavailable as error:", "        except ZeroDivisionError as error:", OWNER, "people_store_unread"),
    ("not_held_as_identity_provider", SCH, "        except OwnerNotHeld as error:", "        except ZeroDivisionError as error:", OWNER, "not_held_is_said"),
    ("run_now_says_next_slot", SCH, "            raise ScheduleRunRefused(_asked_for(refused, recipe)) from refused\n        lock", "            raise ScheduleRunRefused(str(refused)) from refused\n        lock", OWNER, "run_now_and and run_now"),
    ("external_says_next_slot", SCH, "            raise ScheduleRunRefused(_asked_for(refused, recipe)) from refused\n        if Right.RUN_PIPELINES", "            raise ScheduleRunRefused(str(refused)) from refused\n        if Right.RUN_PIPELINES", OWNER, "run_now_and and external"),
    ("rule_out_of_date_as_unreachable", "services/api/rule_schedule.py", "        except PrincipalAccessOutOfDate as error:", "        except ZeroDivisionError as error:", OWNER, "scheduled_rule"),
    ("list_out_of_date_generic", "services/api/list_schedule.py", "    if isinstance(error, PrincipalAccessOutOfDate):", "    if False:", OWNER, "list_refresh or deployment_wide"),
    ("deployment_list_generic", "services/api/app.py", "            return list_owner_refusal_words(error, owner_id)", "            return f\"OspreyFlow could not act as the schedule's owner, {owner_id}\"", OWNER, "deployment_wide"),
    ("watch_out_of_date_as_unreachable", "services/api/monitor_schedule.py", "            if isinstance(error, PrincipalAccessOutOfDate):", "            if False:", OWNER, "watch_s_owner"),
    ("kyc_deployer_words_generic", "services/api/kyc_sweep.py", "                        why = (\n                            f\"its deployer, {rule.owner_id}, {ACCESS_OUT_OF_DATE_WORDS}: \"\n                            f\"{KYC_OUT_OF_DATE_NEXT}\"\n                        )\n", "", OWNER, "kyc_check"),
    ("kyc_says_runs_again", "services/api/kyc_sweep.py", "    \"the documents that lapsed are not judged by this day's check; the rule judges its customers \"\n    \"afresh at its next load\"", "    \"it runs again once they sign in\"", OWNER, "kyc_check"),
    ("kyc_fault_swallowed", "services/api/kyc_sweep.py", "                    except PrincipalExchangeError:  # refused or unreachable: as the None answer", "                    except Exception:  # noqa: BLE001", OWNER, "fault_resolving"),
    ("notice_says_sign_in_did_not_answer", "services/api/schedule_notices.py", "        \"did not run: its owner has not signed in to OspreyFlow within the last 24 hours. It runs \"\n        \"again once they sign in.\"\n", "        \"could not run: the sign-in service did not answer.\"\n", OWNER, "notice"),
]


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | CLOSED
    bad = 0
    for name, path, old, new, test, k in PLANTS:
        full = CORE / path
        src = full.read_text(encoding="utf-8")
        record = out / f"plant_{name}.txt"
        if src.count(old) != 1:
            record.write_text(f"PLANT MISS {name}: the text is not found once\n"); print("MISS", name); bad += 1
            continue
        full.write_text(src.replace(old, new), encoding="utf-8")
        try:
            run = subprocess.run(
                [str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c",
                 "../OspreyFlow_Build/pytest.ini", "-m", "not live", test, "-k", k],
                cwd=CORE, env=env | {"PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}, capture_output=True, text=True)
        finally:
            full.write_text(src, encoding="utf-8")
        lines = [ln for ln in run.stdout.splitlines() if ln.startswith(("FAILED", "E   ")) or " passed" in ln or " failed" in ln]
        state = {0: "GREEN (the plant was not caught)", 5: "MISS (-k selected nothing)"}.get(run.returncode, "RED")
        bad += state != "RED"
        record.write_text(f"# plant: {name} ({path}); fresh PYTHONPYCACHEPREFIX; closed ports; -k {k}\n# {state}\n"
                          + "\n".join(lines[-8:]) + "\n", encoding="utf-8")
        print(name, state, lines[-1] if lines else "")
    return bad


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
