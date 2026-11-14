"""Re-run v052-identities' offline plants at one head, each pytest with a fresh PYTHONPYCACHEPREFIX
(the orchestrator's rule, 13 Nov: a stale .pyc can run the previous plant). Usage: replant.py <worktree> <out dir>"""
import os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
T = "../OspreyFlow_Build/tests/services/"
PA, APP, EP, IA, SI = ("OspreyFlow_Core/packages/principal_auth/__init__.py", "OspreyFlow_Core/services/api/app.py",
    "OspreyFlow_Core/services/api/entra_people.py", "OspreyFlow_Core/services/api/identity_admin.py",
    "OspreyFlow_Core/services/api/service_identity.py")
RS_MAIN, RS_SYNC = "OspreyFlow_Core/services/report_sync/__main__.py", "OspreyFlow_Core/services/report_sync/sync.py"
D, RG, SIE, EPT, ARR, ARO, RST = (T + "api/test_auth_entra_dashboards.py", T + "api/test_route_gate.py",
    T + "api/test_service_identity_entra.py", T + "api/test_entra_people.py", T + "api/test_admin_routes.py",
    T + "api/test_admin_roles_routes.py", T + "report_sync/test_report_sync.py")
OWN = '    own = {mapping.client_id, mapping.api_client_id, *(a for a in audiences if isinstance(a, str))}'
PLANTS = [  # name, file, old, new, test file, -k
 ("any_client_id_under_the_scope", RS_MAIN, "        if scope is not None and (not _APPLICATION_ID.match(client_id) or not secret):", "        if scope is not None and not secret:", RST, "names_the_scope"),
 ("scope_not_sent", RS_SYNC, '                      **({"scope": self._scope} if self._scope else {})},', "                      },", RST, "api_s_scope"),
 ("dashboard_unrouted", PA, "        routes = sorted(DASHBOARD_ROUTES)\n", "", D, "narrow_principal"),
 ("no_role_check", PA, "    if not isinstance(roles, list) or DASHBOARD_APP_ROLE not in roles:", "    if False:", D, "no_registered_dashboard and role"),
 ("tenant_not_pinned", PA, '    if claims.get("tid") != mapping.tenant_id:\n        raise PrincipalResolutionError("token\'s tid is missing or names another tenant")\n', "", D, "another-tenant"),
 ("unregistered_admitted", PA, "        if stored is None:\n            raise PrincipalResolutionError(", '        if stored is None:\n            stored = StoredDashboard(application_id, "OFFICIAL", "u", ())\n        if False:\n            raise PrincipalResolutionError(', D, "unregistered"),
 ("own_client_without_glass_id", PA, OWN, OWN.replace("mapping.client_id, ", ""), D, "no_registered_dashboard or api_s_own"),
 ("own_client_without_api_client_id", PA, OWN, OWN.replace("mapping.api_client_id, ", ""), D, "no_registered_dashboard or api_s_own"),
 ("own_client_without_aud", PA, OWN, "    own = {mapping.client_id, mapping.api_client_id}", D, "no_registered_dashboard or audience"),
 ("v1_client_by_azp_alone", PA, '    named = [claims[c] for c in ("azp", "appid") if c in claims]', '    named = [claims[c] for c in ("azp",) if c in claims]', D, "v1_token"),
 ("resolver_list_claim_unguarded", PA, "    client = named[0] if named and texts and len(set(named)) == 1 else None", "    client = next(iter(set(named))) if len(set(named)) == 1 else None", D, "list_is_refused"),
 ("dashboard_read_unbounded", PA, "                timeout=self._role_lookup_timeout,\n            )\n        except Exception as exc:  # noqa: BLE001 - every failure of the read is the one 503\n            raise PrincipalLookupUnavailable(\n                f\"the dashboard identity", "                timeout=None,\n            )\n        except Exception as exc:  # noqa: BLE001 - every failure of the read is the one 503\n            raise PrincipalLookupUnavailable(\n                f\"the dashboard identity", D, "too_slow"),
 ("keycloak_dashboard_store_accepted", PA, '        elif dashboard_source is not None:\n            raise ValueError("a dashboard store is read only for an Entra ID claim mapping")\n', "", D, "keycloak_mapping"),
 ("no_route_gate", APP, '    if identity.routes is not None:\n        route = request.scope.get("route")', '    if False:\n        route = request.scope.get("route")', RG, "named_routes_is_refused"),
 ("stream_ungated", APP, "    if raw.routes is not None:\n        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)\n        return\n", "", RG, "stream"),
 ("run_api_admits_a_registered_dashboard", APP, "        if registered is not None:\n            raise HTTPException(status_code=403, detail=DASHBOARD_IS_NO_SERVICE_IDENTITY)", "        pass", SIE, "registered_as_a_dashboard"),
 ("run_api_read_unbounded", APP, "                store.dashboard(store.tenant_id, client), timeout=ROLE_LOOKUP_TIMEOUT_SECONDS", "                store.dashboard(store.tenant_id, client), timeout=None", SIE, "answering_none"),
 ("verifier_admits_the_role", SI, "        if isinstance(roles, list) and DASHBOARD_APP_ROLE in roles:", "        if False:", SIE, "dashboard_role_is_no_service"),
 ("run_api_list_claim_unguarded", SI, "        if not named or not all(isinstance(c, str) for c in named) or len(set(named)) != 1:", "        if len(set(named)) != 1:", SIE, "list_is_refused"),
 ("viewer_check_after_the_directory", APP, "    people = await names.people([grantee])\n    if people is not None and grantee in people:\n        return\n", "    people = await names.people([grantee])\n    if people is None or grantee in people:\n        return\n", ARO, "dashboard"),
 ("dashboards_asked_before_the_person", APP, "    people = await names.people([grantee])\n    if people is not None and grantee in people:\n        return\n", "    people = await names.people([grantee])\n", ARO, "granted_without_asking"),
 ("revoke_after_the_removal", APP, "    revoked = [\n        case\n        for account in accounts\n        for case in await investigations.revoke_everywhere(account, by=principal)\n    ]\n    await identity_admin.delete_dashboard(client_id)", "    await identity_admin.delete_dashboard(client_id)\n    revoked = [\n        case\n        for account in accounts\n        for case in await investigations.revoke_everywhere(account, by=principal)\n    ]", ARR, "revoke"),
 ("removal_revokes_nothing", APP, "        for case in await investigations.revoke_everywhere(account, by=principal)\n", "        for case in []\n", ARR, "revokes_every"),
 ("route_drops_application_id", APP, "        body.name, clearance=body.clearance, org_unit=body.org_unit,\n        application_id=body.application_id,", "        body.name, clearance=body.clearance, org_unit=body.org_unit,", ARR, "passes_the_application"),
 ("dashboards_ask_people_s_sign_in", "OspreyFlow_Core/apps/workspace/src/admin/api.ts", 'call<SignInKind>(api, "dashboards/sign-in");', 'call<SignInKind>(api, "sign-in");', None, None),
 ("app_wiring_without_own_clients", APP, "            resources.people_store, own_clients=(mapping.client_id, mapping.api_client_id)\n", "            resources.people_store\n", EPT, "own_applications"),
 ("entra_registers_without_an_id", EP, "        if application_id is None:\n            raise UnknownRoleError(", '        if application_id is None:\n            application_id = "ffffffff-0000-4111-8222-333333333333"\n        if False:\n            raise UnknownRoleError(', EPT, "without_its_application_id"),
 ("own_applications_registered", EP, "        if application_id.lower() in self.own_clients:", "        if False:", EPT, "own_applications"),
 ("name_not_slugged", EP, "            application_id, dashboard_slug(name), clearance=clearance, org_unit=org_unit", "            application_id, name, clearance=clearance, org_unit=org_unit", EPT, "named_as_keycloak"),
 ("keycloak_takes_an_application_id", IA, "        if application_id is not None:\n            raise UnknownRoleError(\n                \"an application id names", "        if False:\n            raise UnknownRoleError(\n                \"an application id names", EPT, "keycloak_an_application_id"),
]
ENV = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
ENV.pop("OSPREY_LANE", None)
head = subprocess.run(["git", "-C", str(W), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
bad = 0
for name, rel, old, new, test, k in PLANTS:
    if test is None:
        continue
    path = W / rel; text = path.read_text()
    if text.count(old) != 1:
        print(f"MISS {name}: {text.count(old)} matches"); bad += 1; continue
    path.write_text(text.replace(old, new))
    try:
        cmd = [".venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", "../OspreyFlow_Build/pytest.ini", test, "-k", k]
        with tempfile.TemporaryDirectory() as pyc:
            run = subprocess.run(cmd, cwd=W / "OspreyFlow_Core", env={**ENV, "PYTHONPYCACHEPREFIX": pyc},
                                 capture_output=True, text=True, stdin=subprocess.DEVNULL)
    finally:
        path.write_text(text)
    lines = [l for l in run.stdout.splitlines() if l.startswith(("FAILED", "ERROR")) or " passed" in l or " failed" in l]
    red = any(l.startswith("FAILED") for l in lines)
    bad += not red
    (OUT / f"plant_{name}.txt").write_text(
        f"# plant: {name} ({rel}), at {head}, re-run with a fresh PYTHONPYCACHEPREFIX\n# replaced: {old!r}\n# with: {new!r}\n"
        f"# run (from OspreyFlow_Core, closed ports): pytest -q -c ../OspreyFlow_Build/pytest.ini {test} -k '{k}'\n" + "\n".join(lines) + "\n")
    print(("RED  " if red else "GREEN") + f" {name}: " + (lines[-1] if lines else "no output"))
dirty = subprocess.run(["git", "-C", str(W), "status", "--short", "--", "OspreyFlow_Core"], capture_output=True, text=True).stdout
print("restored" if not dirty else "DIRTY:\n" + dirty)
sys.exit(1 if bad or dirty else 0)
