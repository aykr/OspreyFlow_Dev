# ruff: noqa: E501 - the plants are the real code's lines, verbatim
"""P10 part 2's planted faults (CLAUDE.md rule 15): each edits the real code where the behaviour
lives, runs the cases meant to catch it, expects them red, and puts the file back. The shared files'
diffs (`readers.diff`, `render.diff`, `glass-sign-in.diff`) are applied first, so a fault in them is
planted where it will merge, and reverted at the end. Run from `OspreyFlow_Core`:

    env -u OSPREY_LANE ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 \\
        CLICKHOUSE_HTTP_PORT=59994 .venv/bin/python \\
        ../OspreyFlow_Build/process/lanes/admin/p10p2/p10p2_plants.py [--live]

`--live` adds the plants whose cases need Postgres (under a lease, with its ports pinned);
`--only-live` runs those alone (and no vitest control: the server need not hold the Glass's packages).

**What counts as red** (as `p10/p10_plants.py`, the orchestrator's review of part 1): the planted
source must still compile (Python) or the plant is a harness fault; a pytest case is red only on
exit 1 with "failed" and no "error" in its summary; a vitest case only on exit 1 with "failed" and
no "Error:" before its summary (a collection or import failure). Anything else is a harness fault.
It refuses to start on a dirty tree, and restores every file in a `finally`.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

CORE = Path.cwd()
ROOT = CORE.parent
HERE = Path(__file__).resolve().parent
DIFFS = [HERE / f"{name}.diff" for name in ("readers", "render", "glass-sign-in")]
T = "../OspreyFlow_Build/tests/"
ENTRA = T + "services/api/test_auth_entra_claims.py"
PEOPLE = T + "services/api/test_entra_people.py"
PEOPLE_LIVE = T + "services/api/test_entra_people_live.py"
SERVICE = T + "services/api/test_service_identity_entra.py"
READERS = T + "harness/test_realm_readers_refuse_entra.py"
RENDER = T + "harness/test_cloud_platform_entra.py"
RENDER_ALL = T + "harness/test_cloud_platform_render.py"
CONTROL = [ENTRA, T + "services/api/test_auth.py", PEOPLE, SERVICE, READERS, RENDER, RENDER_ALL,
           T + "services/api/test_service_identity_and_rollup.py"]  # fmt: skip
GLASS_CONTROL = ["apps/workspace/src/auth", "apps/workspace/src/admin/PeopleEntra.test.tsx"]

PA = "packages/principal_auth/__init__.py"
NO_STORED = """        if stored is None:
            raise PrincipalLookupUnavailable(
                "an Entra principal's roles are read from the deployment's store, and none was read"
            )
"""
EP = "services/api/entra_people.py"
APP = "services/api/app.py"
SI = "services/api/service_identity.py"


def off(line: str) -> tuple[str, str]:
    """The edit that turns one `if`/`elif` line's condition off, at that line's own indentation."""
    assert line.endswith(":\n"), line
    stripped = line.lstrip(" ")
    indent = line[: len(line) - len(stripped)]
    keyword = "elif" if stripped.startswith("elif ") else "if"
    return line, f"{indent}{keyword} False:\n"


@dataclass
class Plant:
    name: str
    target: str
    edits: list[tuple[str, str]]
    cases: list[str]  # pytest node ids (path::name) or "vitest:<file>::<name>"
    live: bool = False
    notes: list[str] = field(default_factory=list)


PLANTS = [
    # --- principal_auth: the carries ---
    Plant(
        "a member's idp compared to iss as a string (the old guest check)",
        PA,
        [
            (
                '_tenant_of_entra_issuer(claims["idp"]) != mapping.tenant_id',
                'claims["idp"] != claims.get("iss")',
            )
        ],
        [
            f"{ENTRA}::test_a_member_whose_idp_names_our_tenant_in_either_form_resolves[member-v1-form]"
        ],
    ),
    Plant(
        "an idp naming no Entra issuer admitted (only another tenant's refused)",
        PA,
        [
            (
                '_tenant_of_entra_issuer(claims["idp"]) != mapping.tenant_id',
                '_tenant_of_entra_issuer(claims["idp"]) not in (None, mapping.tenant_id)',
            )
        ],
        [
            f"{ENTRA}::test_an_idp_naming_no_entra_issuer_of_our_tenant_is_a_guest[msa]",
            f"{ENTRA}::test_an_idp_naming_no_entra_issuer_of_our_tenant_is_a_guest[federated]",
        ],
    ),
    Plant(
        "client_id or scope accepted and ignored without a tenant",
        PA,
        [
            off(
                "        if self.tenant_id is None and (self.client_id is not None or self.scope != DEFAULT_SCOPE):\n"
            )
        ],
        [
            f"{ENTRA}::test_a_client_or_scope_without_a_tenant_is_refused[client]",
            f"{ENTRA}::test_a_client_or_scope_without_a_tenant_is_refused[scope]",
        ],
    ),
    Plant(
        "the app-only check removed (its cases red by the app-only words, never an AttributeError)",
        PA,
        [
            off(
                '        if claims.get("idtyp") == "app" or not isinstance(scope, str) or not scope:\n'
            )
        ],
        [
            f"{ENTRA}::test_an_app_only_token_is_no_person[app-token]",
            f"{ENTRA}::test_an_app_only_token_is_no_person[no-scp]",
            f"{ENTRA}::test_an_app_only_token_is_no_person[idtyp-app]",
        ],
    ),
    # --- principal_auth: the stored person ---
    Plant(
        "an Entra principal's roles read from its token",
        PA,
        [
            (
                "        roles = _stored_roles(stored)\n",
                '        roles = _string_list(claims, CLAIM_ROLES, "roles")\n',
            )
        ],
        [
            f"{ENTRA}::test_an_entra_principals_roles_are_the_stored_ones_never_the_tokens",
            f"{ENTRA}::test_an_entra_app_role_grants_no_ospreyflow_role",
            f"{PEOPLE}::test_me_answers_the_resolved_principal_never_the_tokens_roles",
        ],
    ),
    Plant(
        "a person disabled here admitted",
        PA,
        [off("        if stored.disabled:\n")],
        [
            f"{ENTRA}::test_a_person_disabled_here_is_refused",
            f"{PEOPLE}::test_me_for_a_person_disabled_here_is_refused",
        ],
    ),
    Plant(
        "a failed read answered as a person with no roles",
        PA,
        [
            (
                """        except Exception as exc:  # noqa: BLE001 - every failure of the read is the one 503
            raise PrincipalLookupUnavailable(
                f"the person's stored roles could not be read: {type(exc).__name__}"
            ) from exc
""",
                """        except Exception:  # noqa: BLE001
            stored = StoredPerson(roles=(), disabled=False)
""",
            )
        ],
        [
            f"{ENTRA}::test_a_failed_or_slow_lookup_is_unavailable_never_a_principal[raises]",
            f"{ENTRA}::test_a_failed_or_slow_lookup_is_unavailable_never_a_principal[slow]",
            f"{PEOPLE}::test_a_session_whose_roles_cannot_be_read_is_a_503",
        ],
    ),
    Plant(
        "the store read before the token's refusals",
        PA,
        [
            (
                "        verified = _verified_parts(claims, self._claim_mapping)\n        assert self._role_source",
                "        await self._role_source.person(  # type: ignore[union-attr]\n"
                "            str(self._claim_mapping.tenant_id), str(claims.get('oid')), None  # type: ignore[arg-type]\n"
                "        )\n"
                "        verified = _verified_parts(claims, self._claim_mapping)\n        assert self._role_source",
            )
        ],
        [
            f"{ENTRA}::test_a_refused_token_records_nobody",
            f"{PEOPLE}::test_me_for_another_tenants_token_is_refused",
        ],
    ),
    Plant(
        "the synchronous path builds an Entra principal without its stored roles (both guards)",
        PA,
        [
            (
                '''        if self._claim_mapping.is_entra:
            raise PrincipalLookupUnavailable(
                "an Entra principal is resolved with its stored roles (resolve_principal)"''',
                '''        if False:
            raise PrincipalLookupUnavailable(
                "an Entra principal is resolved with its stored roles (resolve_principal)"''',
            ),
            (
                NO_STORED,
                "        if stored is None:\n            stored = StoredPerson(roles=(), disabled=False)\n",
            ),
        ],
        [f"{ENTRA}::test_the_synchronous_path_refuses_an_entra_mapping"],
    ),
    Plant(
        "the construction path builds an Entra principal with no stored person",
        PA,
        [
            (
                NO_STORED,
                "        if stored is None:\n            stored = StoredPerson(roles=(), disabled=False)\n",
            )
        ],
        [
            f"{ENTRA}::test_the_construction_path_refuses_an_entra_principal_without_its_stored_person"
        ],
    ),
    Plant(
        "an Entra resolver built with no people store",
        PA,
        [off("            if role_source is None:\n")],
        [f"{ENTRA}::test_an_entra_mapping_needs_a_people_store_and_keycloak_refuses_one"],
    ),
    Plant(
        "owner resolution by exchange on Entra",
        PA,
        [
            (
                """        if self._claim_mapping.is_entra:
            # Entra has no impersonation exchange""",
                """        if False:
            # Entra has no impersonation exchange""",
            )
        ],
        [
            f"{ENTRA}::test_owner_resolution_is_unavailable_on_entra_even_with_an_exchange_configured"
        ],
    ),
    Plant(
        "a mapping in the environment that is not JSON falls back to the fixed names",
        PA,
        [
            (
                '            raise ValueError(f"{CLAIM_MAPPING_VARIABLE} is not JSON: {exc}") from None\n',
                "            return DEFAULT_CLAIM_MAPPING\n",
            )
        ],
        [
            f"{ENTRA}::test_a_mapping_in_the_environment_that_does_not_load_stops_the_start[not-json]"
        ],
    ),
    # --- the people store and Admin › People ---
    Plant(
        "no first administrator named, and the start goes on",
        EP,
        [off("    if not oids:\n")],
        [
            f"{PEOPLE}::test_first_administrators_none_or_malformed_stop_the_start['']",
            f"{PEOPLE}::test_an_entra_mapping_with_no_first_administrator_does_not_start",
        ],
    ),
    Plant(
        "adding by object id without manage_people",
        APP,
        [
            (
                """    "/v1/admin/people/by-object-id",
    status_code=201,
    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],""",
                """    "/v1/admin/people/by-object-id",
    status_code=201,""",
            )
        ],
        [f"{PEOPLE}::test_adding_a_person_needs_manage_people"],
    ),
    Plant(
        "the sign-in kind without manage_people",
        APP,
        [
            (
                """@app.get("/v1/admin/sign-in", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))])""",
                """@app.get("/v1/admin/sign-in")""",
            )
        ],
        [f"{PEOPLE}::test_the_sign_in_kind_needs_manage_people"],
    ),
    Plant(
        "adding by object id on Keycloak",
        APP,
        [off("    if not isinstance(identity_admin, EntraPeopleAdmin):\n")],
        [f"{PEOPLE}::test_adding_by_object_id_is_refused_on_keycloak"],
    ),
    Plant(
        "a session whose roles cannot be read let through as an error, not a 503",
        APP,
        [
            (
                """    except PrincipalLookupUnavailable as exc:
        # ADR-148 Amendment 8: the person's stored roles could not be read; never a principal
        # without them.
""",
                """    except ZeroDivisionError as exc:
""",
            )
        ],
        [f"{PEOPLE}::test_a_session_whose_roles_cannot_be_read_is_a_503"],
    ),
    Plant(
        "an invite on Entra answered as if made",
        EP,
        [
            (
                '        raise _refused("People are not invited here.")\n',
                "        return None  # type: ignore[return-value]\n",
            )
        ],
        [f"{PEOPLE}::test_what_entra_holds_is_refused_in_words[invite]"],
    ),
    Plant(
        "the store reads every tenant's row for an object id",
        EP,
        [
            (
                '"receivable_handling_codes FROM entra_people WHERE tenant_id = $1 AND oid = $2",',
                '"receivable_handling_codes FROM entra_people WHERE ($1::text IS NOT NULL) AND oid = $2",',
            )
        ],
        [f"{PEOPLE_LIVE}::test_another_tenants_row_for_the_same_oid_grants_nothing"],
        live=True,
    ),
    Plant(
        "first administrators re-granted at every start",
        EP,
        [
            (
                "\"VALUES ($1, $2, $3, 'install') ON CONFLICT (tenant_id, oid) DO NOTHING\",",
                "\"VALUES ($1, $2, $3, 'install') ON CONFLICT (tenant_id, oid) DO UPDATE SET roles = EXCLUDED.roles\",",
            )
        ],
        [f"{PEOPLE_LIVE}::test_first_administrators_are_seeded_once_and_a_removal_stands"],
        live=True,
    ),
    # --- the service identity ---
    Plant(
        "a service identity's tenant not pinned",
        SI,
        [off('        if claims.get("tid") != self._mapping.tenant_id:\n')],
        [
            f"{SERVICE}::test_what_is_no_service_identity_on_entra_is_refused[other-tenant]",
            f"{SERVICE}::test_what_is_no_service_identity_on_entra_is_refused[no-tid]",
        ],
    ),
    Plant(
        "a person's delegated token taken for a service identity",
        SI,
        [off('        if "scp" in claims or claims.get("idtyp", "app") != "app":\n')],
        [
            f"{SERVICE}::test_what_is_no_service_identity_on_entra_is_refused[a-persons-delegated-token]",
            f"{SERVICE}::test_what_is_no_service_identity_on_entra_is_refused[idtyp-user]",
        ],
    ),
    Plant(
        "the Glass's or this API's own registration taken for an orchestrator",
        SI,
        [off("        if client in (self._mapping.client_id, self._config.oidc_audience):\n")],
        [
            f"{SERVICE}::test_what_is_no_service_identity_on_entra_is_refused[the-glass]",
            f"{SERVICE}::test_what_is_no_service_identity_on_entra_is_refused[this-api-itself]",
        ],
    ),
    Plant(
        "an Entra token under Keycloak's handling taken by its preferred_username",
        SI,
        [off('        if "tid" in claims:\n')],
        [f"{SERVICE}::test_an_entra_token_under_keycloaks_handling_is_refused[our-tenant]"],
    ),
    # --- the realm's readers (readers.diff) ---
    Plant(
        "the console's /admin admits an Entra token's app role",
        "harness/webapp_auth.py",
        [off('    if "tid" in claims:\n')],
        [f"{READERS}::test_the_consoles_admin_refuses_an_entra_token_with_the_admin_role[entra]"],
    ),
    Plant(
        "the realm's sign-in admits an Entra ID token",
        "harness/oidc.py",
        [off('    if "tid" in claims:\n')],
        [f"{READERS}::test_the_realms_sign_in_refuses_an_entra_id_token"],
    ),
    Plant(
        "Superset reads token roles on Entra",
        "deploy/superset/superset_config.py",
        [
            (
                '"role_keys": [] if _ENTRA else claims.get("roles", []),',
                '"role_keys": claims.get("roles", []),',
            )
        ],
        [f"{READERS}::test_superset_reads_no_token_role_on_entra[entra]"],
    ),
    # --- the render (render.diff) ---
    Plant(
        "the Glass's client left out of the rendered claim mapping",
        "packages/schemas/deployment.py",
        [('            "client_id": self.client_id,\n', "")],
        [
            f"{RENDER}::test_the_rendered_settings_sign_in_a_glass_token_through_the_one_construction_path"
        ],
    ),
    Plant(
        "the realm's settings the cluster's install writes left in",
        "harness/cloud_platform/__init__.py",
        [
            (
                "    environment.update({k: v for k, v in install.settings.items() if k not in REALM_SETTINGS})\n",
                "    environment.update(install.settings)\n",
            )
        ],
        [f"{RENDER}::test_the_realms_settings_are_gone_and_entras_are_rendered"],
    ),
    Plant(
        "Entra's settings written before the install's, which overwrite them",
        "harness/cloud_platform/__init__.py",
        [
            (
                """    environment.update({k: v for k, v in install.settings.items() if k not in REALM_SETTINGS})
    # Entra ID's, last, so nothing the cluster's realm wrote stands (ADR-148 Amendment 8).
    environment.update(entra_settings(config))
""",
                """    environment.update(entra_settings(config))
    environment.update(install.settings)
""",
            )
        ],
        [
            f"{RENDER}::test_the_realms_settings_are_gone_and_entras_are_rendered",
            f"{RENDER}::test_v1_tokens_and_a_claims_mapping_policy_change_the_issuer_audience_and_keys",
        ],
    ),
    Plant(
        "an empty list of first administrators accepted",
        "packages/schemas/deployment.py",
        [off("        if not oids:\n")],
        [f"{RENDER}::test_no_first_administrator_is_refused_never_everyone"],
    ),
    Plant(
        "a render with no Entra sign-in let through",
        "harness/cloud_platform/__init__.py",
        [off("    if claims is None:\n")],
        [f"{RENDER}::test_a_render_without_entra_sign_in_is_refused_in_words"],
    ),
    Plant(
        "Keycloak rendered",
        "harness/cloud_platform/__init__.py",
        [
            (
                '    {"proxy", "ollama", "ollama-models", "whisper", "whisper-models", "keycloak"}\n',
                '    {"proxy", "ollama", "ollama-models", "whisper", "whisper-models"}\n',
            )
        ],
        [f"{RENDER_ALL}::test_no_pod_takes_group_0_and_keycloak_is_not_rendered[development]"],
    ),
    Plant(
        "Keycloak's deployment.json given a sign_in",
        "harness/site.py",
        [
            (
                "    if entra is not None:\n        del settings",
                '    settings["sign_in"] = None\n    if entra is not None:\n        del settings',
            )
        ],
        [f"{RENDER}::test_keycloaks_deployment_file_is_as_it_was"],
    ),
    # --- the Glass (glass-sign-in.diff) ---
    Plant(
        "Entra's sign-in taken from an authority that is not Entra's",
        "apps/workspace/src/auth/oidcConfig.ts",
        [
            (
                '  if (typeof authority !== "string" || !/^https:\\/\\/login\\.microsoftonline\\.com\\/[0-9a-f-]{36}\\/v2\\.0$/.test(authority)) return null;\n',
                '  if (typeof authority !== "string") return null;\n',
            )
        ],
        [
            "vitest:apps/workspace/src/auth/oidcConfig.test.ts::is not taken from an authority that is not Entra's"
        ],
    ),
    Plant(
        "the shown clearance read from the ID token again",
        "apps/workspace/src/auth/userManager.ts",
        [
            (
                "    clearance: me.clearance,\n",
                "    clearance: String((session as unknown as { profile?: Record<string, unknown> })?.profile?.clearance ?? me.clearance),\n",
            )
        ],
        [
            "vitest:apps/workspace/src/auth/resolvedPrincipal.test.ts::is read nowhere in apps/workspace/src"
        ],
    ),
    Plant(
        "a guess when /v1/me does not answer",
        "apps/workspace/src/auth/userManager.ts",
        [
            (
                "    if (!response.ok) return null;\n",
                '    if (!response.ok) return { id: "", clearance: "OFFICIAL", org_unit: "", roles: [], receivable_handling_codes: [] };\n',
            )
        ],
        [
            "vitest:apps/workspace/src/auth/resolvedPrincipal.test.ts::is none after a refusal, never a guess"
        ],
    ),
    Plant(
        "People on Entra offers Access",
        "apps/workspace/src/admin/sections/People.tsx",
        [
            (
                "            {!entra && (\n              <Button aria-label={`Edit access for ${person.username}`}",
                "            {(\n              <Button aria-label={`Edit access for ${person.username}`}",
            )
        ],
        [
            "vitest:apps/workspace/src/admin/PeopleEntra.test.tsx::says Entra holds the accounts and offers add by object id, never invite, access, reset or remove"
        ],
    ),
]


def run_pytest(nodeids: list[str]) -> tuple[int, str]:
    done = subprocess.run(
        [str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", *nodeids],
        capture_output=True, text=True, cwd=CORE,
    )  # fmt: skip
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return done.returncode, lines[-1] if lines else done.stderr[-300:]


def run_vitest(case: str) -> tuple[int, str]:
    path, name = case.removeprefix("vitest:").split("::", 1)
    done = subprocess.run(
        ["npx", "vitest", "run", path, "-t", name], capture_output=True, text=True, cwd=CORE
    )
    out = done.stdout + done.stderr
    summary = next(
        (line.strip() for line in out.splitlines() if line.strip().startswith("Tests")), ""
    )
    collect = "Error:" in out.split("Tests", 1)[0] and "AssertionError" not in out
    return done.returncode, summary + (" [collection error]" if collect else "")


def verdict(rc: int, tail: str, vitest: bool) -> str:
    if vitest:
        if rc == 1 and "failed" in tail and "[collection error]" not in tail:
            return "red"
        return "MISSED" if rc == 0 else "HARNESS FAULT"
    if rc == 0:
        return "MISSED"
    if rc == 1 and "failed" in tail and "error" not in tail:
        return "red"
    return "HARNESS FAULT"


def git(*args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=check
    ).stdout


def main() -> int:
    only_live = "--only-live" in sys.argv
    live = "--live" in sys.argv or only_live
    if git("status", "--porcelain", "--", "OspreyFlow_Core", "OspreyFlow_Build/tests").strip():
        print("refused: the tree has uncommitted changes")
        return 2
    for diff in DIFFS:
        git("apply", str(diff))
    originals: dict[str, str] = {}
    reds = missed = faults = runs = 0
    try:
        rc, tail = run_pytest(CONTROL)
        print(
            f"control (diffs applied, no plant): {'green' if rc == 0 else 'RED'} (exit {rc}) — {tail}"
        )
        vrc = (
            0
            if only_live
            else subprocess.run(
                ["npx", "vitest", "run", *GLASS_CONTROL], cwd=CORE, capture_output=True
            ).returncode
        )
        print(f"glass control: {'green' if vrc == 0 else 'RED'} (exit {vrc})")
        if rc != 0 or vrc != 0:
            return 1
        for plant in PLANTS:
            if only_live and not plant.live:
                continue
            if plant.live and not live:
                print(f"[{plant.name}] live: run with --live under a lease")
                continue
            path = CORE / plant.target
            original = originals.setdefault(plant.target, path.read_text())
            planted = original
            for old, new in plant.edits:
                if planted.count(old) != 1:
                    print(
                        f"HARNESS FAULT, plant misses its site ({planted.count(old)}): {plant.name}"
                    )
                    faults += 1
                    break
                planted = planted.replace(old, new)
            else:
                if path.suffix == ".py":
                    try:
                        compile(planted, str(path), "exec")
                    except SyntaxError as exc:
                        print(
                            f"HARNESS FAULT, planted source does not compile ({exc}): {plant.name}"
                        )
                        faults += 1
                        continue
                path.write_text(planted)
                try:
                    for case in plant.cases:
                        vitest = case.startswith("vitest:")
                        rc, tail = run_vitest(case) if vitest else run_pytest([case])
                        result = verdict(rc, tail, vitest)
                        runs += 1
                        reds += result == "red"
                        missed += result == "MISSED"
                        faults += result == "HARNESS FAULT"
                        print(
                            f"[{plant.name}] {case.split('::')[-1]}: {result} (exit {rc}) — {tail}"
                        )
                finally:
                    path.write_text(original)
    finally:
        for target, text in originals.items():
            (CORE / target).write_text(text)
        for diff in reversed(DIFFS):
            git("apply", "-R", str(diff))
    rc, tail = run_pytest(CONTROL[:4])
    print(f"control (restored, branch alone): {'green' if rc == 0 else 'RED'} (exit {rc}) — {tail}")
    print(
        f"{len(PLANTS)} plants, {runs} case runs: {reds} red, {missed} missed, {faults} harness faults"
    )
    return 1 if missed or faults or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
