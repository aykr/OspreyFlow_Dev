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
DIFFS = [HERE / f"{name}.diff" for name in ("readers", "render", "glass-sign-in", "runbook")]
T = "../OspreyFlow_Build/tests/"
ENTRA = T + "services/api/test_auth_entra_claims.py"
PEOPLE = T + "services/api/test_entra_people.py"
PEOPLE_LIVE = T + "services/api/test_entra_people_live.py"
SERVICE = T + "services/api/test_service_identity_entra.py"
READERS = T + "harness/test_realm_readers_refuse_entra.py"
RENDER = T + "harness/test_cloud_platform_entra.py"
RENDER_ALL = T + "harness/test_cloud_platform_render.py"
POC = T + "harness/test_cloud_platform_poc.py"
CONTROL = [ENTRA, T + "services/api/test_auth.py", PEOPLE, SERVICE, READERS, RENDER, RENDER_ALL, POC,
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
            (
                "        if self.tenant_id is None and (\n            self.client_id is not None",
                "        if False and (\n            self.client_id is not None",
            )
        ],
        [
            f"{ENTRA}::test_a_client_or_scope_without_a_tenant_is_refused[client]",
            f"{ENTRA}::test_a_client_or_scope_without_a_tenant_is_refused[api-client]",
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
                '"receivable_handling_codes, access_read_at, now() AS at "\n                "FROM entra_people WHERE tenant_id = $1 AND oid = $2",',
                '"receivable_handling_codes, access_read_at, now() AS at "\n                "FROM entra_people WHERE ($1::text IS NOT NULL) AND oid = $2",',
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
                '"SET roles = EXCLUDED.roles WHERE cardinality(entra_people.roles) = 0",',
                '"SET roles = EXCLUDED.roles",',
            )
        ],
        [f"{PEOPLE_LIVE}::test_first_administrators_are_seeded_once_and_a_removal_stands"],
        live=True,
    ),
    # --- the delta socket (the lane review's finding 1) ---
    Plant(
        "an open socket's next message admitted without asking the store",
        APP,
        [
            (
                "        if await _socket_standing(app_, raw) is not None:\n            return None\n",
                "",
            )
        ],
        [
            f"{PEOPLE}::test_an_open_socket_is_closed_at_its_next_message_once_the_person_no_longer_stands[disabled-mid-socket]",
            f"{PEOPLE}::test_an_open_socket_is_closed_at_its_next_message_once_the_person_no_longer_stands[roles-taken-away]",
        ],
    ),
    Plant(
        "a person disabled here still stands at the socket",
        APP,
        [("    if stored is None or stored.disabled:\n", "    if stored is None:\n")],
        [f"{PEOPLE}::test_a_socket_stands_only_while_the_store_says_so[disabled]"],
    ),
    Plant(
        "a store that cannot answer leaves the socket open",
        APP,
        [("        return status.WS_1013_TRY_AGAIN_LATER\n", "        return None\n")],
        [
            f"{PEOPLE}::test_a_socket_stands_only_while_the_store_says_so[store-down]",
            f"{PEOPLE}::test_an_open_socket_is_closed_at_its_next_message_once_the_person_no_longer_stands[store-down]",
        ],
    ),
    Plant(
        "a ticket minted before a disable admitted at connect",
        APP,
        [
            (
                "    if (refused := await _socket_standing(websocket.app, raw)) is not None:\n"
                "        await websocket.close(code=refused)\n        return\n",
                "",
            )
        ],
        [f"{PEOPLE}::test_the_stream_asks_the_store_before_its_first_send"],
    ),
    Plant(
        "a duplicate object id answered in a sign-in name's words",
        EP,
        [
            (
                """        try:
            return await self.store.add(oid, by)
        except PersonExistsError:
            raise PersonActionRefused(
                "person_exists", f"{oid} is already in People: give them roles there."
            ) from None""",
                "        return await self.store.add(oid, by)",
            )
        ],
        [f"{PEOPLE}::test_adding_a_person_already_recorded_is_refused"],
    ),
    Plant(
        "a removal on Entra answered as if made",
        EP,
        [
            (
                """        raise _refused(
            "A person is not removed here""",
                """        return None  # type: ignore[return-value]
        raise _refused(
            "A person is not removed here""",
            )
        ],
        [f"{PEOPLE}::test_the_rest_of_what_entra_holds_is_refused_in_words[remove]"],
    ),
    Plant(
        "the socket's read takes any tenant's row for an object id",
        EP,
        [
            (
                '"SELECT roles, disabled FROM entra_people WHERE tenant_id = $1 AND oid = $2",',
                '"SELECT roles, disabled FROM entra_people WHERE ($1::text IS NOT NULL) AND oid = $2",',
            )
        ],
        [f"{PEOPLE_LIVE}::test_the_sockets_read_is_this_tenants_and_records_nobody"],
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
        [
            (
                "        if client in (\n            self._mapping.client_id,\n",
                "        if False and client in (\n            self._mapping.client_id,\n",
            )
        ],
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
    Plant(
        "the API's own registration taken for an orchestrator on v1.0 tokens",
        SI,
        [("            self._mapping.api_client_id,\n", "")],
        [f"{SERVICE}::test_on_v1_tokens_this_apis_own_registration_is_no_orchestrator"],
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
    Plant(
        "report sync or Superset rendered on cloud-platform",
        "harness/cloud_platform/__init__.py",
        [off("    if config.reporting.sync or config.reporting.superset:\n")],
        [
            f"{RENDER}::test_report_sync_or_superset_switched_on_is_refused_naming_its_step[sync]",
            f"{RENDER}::test_report_sync_or_superset_switched_on_is_refused_naming_its_step[superset]",
        ],
    ),
    Plant(
        "one of the realm's settings dropped from the list the render strips",
        "harness/cloud_platform/__init__.py",
        [('"OIDC_ADMIN_USERS_URL",\n', "")],
        [f"{RENDER}::test_the_realms_settings_are_gone_and_entras_are_rendered"],
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
    Plant(
        "the disabled refusal shown as a misconfiguration",
        "apps/workspace/src/App.tsx",
        [("    if (refusal && (await isDisabledRefusal(refusal))) {\n", "    if (false) {\n")],
        [
            "vitest:apps/workspace/src/App.test.tsx::the Conduit's disabled refusal is shown in its own words, not as a misconfiguration"
        ],
    ),
    Plant(
        "the disabled words found inside other words",
        "apps/workspace/src/auth/disabledAccount.ts",
        [
            (
                "    return body.detail === CONDUIT_DISABLED_DETAIL;\n",
                '    return typeof body.detail === "string" && body.detail.includes(CONDUIT_DISABLED_DETAIL);\n',
            )
        ],
        [
            "vitest:apps/workspace/src/auth/disabledAccount.test.ts::never from the words inside other words"
        ],
    ),
    Plant(
        "the source check blind to an alias of the profile",
        "apps/workspace/src/auth/resolvedPrincipal.test.ts",
        [("  return aliases.some(", "  return false && aliases.some(")],
        [
            "vitest:apps/workspace/src/auth/resolvedPrincipal.test.ts::catches const c = user.profile; return c.roles;"
        ],
    ),
    # --- the orchestrator's review of 3848c32 (12 November 2026) ---
    Plant(
        "item 6: Admin › People lists every tenant's rows",
        EP,
        [('"SELECT * FROM entra_people WHERE tenant_id = $1", self.tenant_id', '"SELECT * FROM entra_people WHERE $1::text IS NOT NULL", self.tenant_id')],
        [f"{PEOPLE_LIVE}::test_another_tenants_row_for_the_same_oid_grants_nothing",
         f"{PEOPLE_LIVE}::test_the_sockets_read_is_this_tenants_and_records_nobody"],
        live=True,
    ),
    Plant(
        "item 6: one person read from any tenant",
        EP,
        [('"SELECT * FROM entra_people WHERE tenant_id = $1 AND oid = $2", self.tenant_id, oid', '"SELECT * FROM entra_people WHERE $1::text IS NOT NULL AND oid = $2", self.tenant_id, oid')],
        [f"{PEOPLE_LIVE}::test_one_person_is_read_by_this_tenant_alone"],
        live=True,
    ),
    Plant(
        "item 6: a role or Disable written to every tenant's row",
        EP,
        [('f"UPDATE entra_people SET {column} = $3 WHERE tenant_id = $1 AND oid = $2 "', 'f"UPDATE entra_people SET {column} = $3 WHERE $1::text IS NOT NULL AND oid = $2 "')],
        [f"{PEOPLE_LIVE}::test_another_tenants_row_for_the_same_oid_grants_nothing",
         f"{PEOPLE_LIVE}::test_adding_by_object_id_once_and_the_refusals_the_fakes_model"],
        live=True,
    ),
    Plant(
        "item 4(a): a named first administrator holding no role never given Admin again",
        EP,
        [("\"VALUES ($1, $2, $3, 'install') ON CONFLICT (tenant_id, oid) DO UPDATE \"\n                    \"SET roles = EXCLUDED.roles WHERE cardinality(entra_people.roles) = 0\",",
          "\"VALUES ($1, $2, $3, 'install') ON CONFLICT (tenant_id, oid) DO NOTHING\",")],
        [f"{PEOPLE_LIVE}::test_a_named_first_administrator_holding_no_role_is_given_admin_again"],
        live=True,
    ),
    Plant(
        "item 5: a sign-in's access read never recorded as read",
        EP,
        [('"COALESCE(entra_people.first_seen, now()), access_read_at = now(), "', '"COALESCE(entra_people.first_seen, now()), "'),
         ('"VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now(), now()) "', '"VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now(), NULL) "')],
        [f"{PEOPLE_LIVE}::test_a_sign_in_records_when_access_was_read_and_an_added_person_has_not_signed_in"],
        live=True,
    ),
    Plant(
        "item 4(b): a manager who never signed in counted as one who can administer",
        "services/api/custom_roles.py",
        [("        and p.signed_in\n", "")],
        [f"{PEOPLE}::test_a_manager_who_never_signed_in_is_no_proof_anyone_can_administer"],
    ),
    Plant(
        "item 5: a transfer to someone whose access is a day old",
        "services/api/admin_people.py",
        [off("        elif to in who.stale:\n")],
        [f"{PEOPLE}::test_a_transfer_to_someone_whose_access_is_a_day_old_is_refused_in_words[stale]"],
    ),
    Plant(
        "item 5: nobody's access judged stale",
        "services/api/admin_people.py",
        [("        stale=frozenset(a for a, p in by_account.items() if not access_current(p, now)),\n", "")],
        [f"{PEOPLE}::test_a_transfer_to_someone_whose_access_is_a_day_old_is_refused_in_words[stale]"],
    ),
    Plant(
        "item 5: a promotions alert to someone whose access is a day old",
        "services/api/promotion_ageing.py",
        [("    return sorted(person.id for person in reviewers if access_current(person))\n", "    return sorted(person.id for person in reviewers)\n")],
        [f"{PEOPLE}::test_a_promotions_alert_skips_someone_whose_access_is_a_day_old[stale]"],
    ),
    Plant(
        "item 5: a reviewer left out of an alert without words",
        "services/api/promotion_ageing.py",
        [off("    if stale:\n")],
        [f"{PEOPLE}::test_a_promotions_alert_skips_someone_whose_access_is_a_day_old[stale]"],
    ),
    Plant(
        "item 5: a day-old read taken as current",
        EP,
        [("    return (now or datetime.now(UTC)) - person.access_read_at <= ACCESS_FRESH\n", "    return True\n")],
        [f"{PEOPLE}::test_a_transfer_to_someone_whose_access_is_a_day_old_is_refused_in_words[stale]",
         f"{PEOPLE}::test_a_promotions_alert_skips_someone_whose_access_is_a_day_old[stale]"],
    ),
    Plant(
        "item 7: a bearer whose roles cannot be read left to the exception",
        APP,
        [("    except PrincipalLookupUnavailable:\n        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)\n        return\n    # ADR-148 Amendment 8: a ticket minted", "    # ADR-148 Amendment 8: a ticket minted")],
        [f"{PEOPLE}::test_a_bearer_whose_roles_cannot_be_read_is_closed_try_again_later[roles-unreadable]"],
    ),
    Plant(
        "item 8: an unknown key id fetched again every time",
        PA,
        [("                UNKNOWN_KID_REFETCH_SECONDS\n            ):\n", "                0\n            ):\n")],
        [f"{ENTRA}::test_an_unknown_kid_is_fetched_for_at_most_once_in_five_minutes"],
    ),
    Plant(
        "item 8: the keys read on the event loop",
        PA,
        [("asyncio.to_thread(self._verified_claims, token), timeout=KEYS_TIMEOUT_SECONDS + 1", "asyncio.sleep(0, self._verified_claims(token)), timeout=KEYS_TIMEOUT_SECONDS + 1")],
        [f"{ENTRA}::test_a_slow_identity_provider_never_holds_the_event_loop"],
    ),
    Plant(
        "item 8: unreachable keys said as a rejected token",
        PA,
        [('            raise SigningKeysUnavailable(\n                "sign-in is unavailable: the identity provider\'s signing keys could not be read"\n            ) from exc\n',
          '            raise PrincipalResolutionError("token rejected: no keys") from exc\n')],
        [f"{ENTRA}::test_an_unreachable_identity_provider_is_a_503_in_words_not_a_rejected_token"],
    ),
    Plant(
        "item 8: the Conduit's 503 in words dropped",
        APP,
        [("    except SigningKeysUnavailable as exc:\n", "    except ZeroDivisionError as exc:\n")],
        [f"{ENTRA}::test_an_unreachable_identity_provider_is_a_503_in_words_not_a_rejected_token"],
    ),
    Plant(
        "note: Entra's algorithms taken from OIDC_ALGORITHMS",
        PA,
        [("            list(ENTRA_ALGORITHMS) if mapping.is_entra else list(config.oidc_algorithms)\n", "            list(config.oidc_algorithms)\n")],
        [f"{ENTRA}::test_an_entra_mapping_takes_rs256_alone_whatever_oidc_algorithms_says"],
    ),
    Plant(
        "note: no leeway on a token's expiry",
        PA,
        [("                leeway=LEEWAY_SECONDS,\n", "")],
        [f"{ENTRA}::test_a_token_a_little_past_its_expiry_is_given_sixty_seconds[30s]"],
    ),
    Plant(
        "note: a service identity's token without an expiry",
        SI,
        [('                    "require": ["sub", "exp"],\n', '                    "require": ["sub"],\n')],
        [f"{SERVICE}::test_a_service_identitys_token_without_an_expiry_is_refused"],
    ),
    Plant(
        "note: the Glass asks Entra without `profile`",
        "harness/site.py",
        [('"scope": f"openid profile {entra.id_uri}/{entra.scope}",', '"scope": f"openid {entra.id_uri}/{entra.scope}",')],
        [f"{RENDER}::test_the_glass_is_told_entras_sign_in"],
    ),
    Plant(
        "note: the set-up console rendered on the profile",
        "harness/cloud_platform/__init__.py",
        [('    jobs = [j for j in values["jobs"] if j["name"] not in NOT_RENDERED]\n',
          '    jobs = [j for j in values["jobs"] if j["name"] not in NOT_RENDERED]\n    workloads.append({**workloads[0], "name": "console", "image": workloads[0]["image"].replace("/workspace:", "/harness:"), "command": ["python", "-m", "harness.webapp"]})\n')],
        [f"{RENDER}::test_the_set_up_console_is_no_part_of_the_render[production]"],
    ),
    Plant(
        "item 4(c): the runbook says nothing of the way back in",
        "harness/cloud_platform/runbooks.py",
        [("**If no administrator is left** (each has left, or lost the Admin role): add the Entra object id of\n", "(each has left, or lost the Admin role): add the Entra object id of\n")],
        [f"{POC}::test_the_install_runbook_says_how_to_recover_when_no_administrator_is_left"],
    ),
    Plant(
        "item 3: a /v1/me that fails once strands the person",
        "apps/workspace/src/App.tsx",
        [("/> : accountUnread}", "/> : null}"), ("            {accountUnread}\n", "")],
        ["vitest:apps/workspace/src/App.test.tsx::it says so, offers Try again and Sign out, and Try again reads it afresh"],
    ),
    Plant(
        "item 3: Try again never asks /v1/me afresh",
        "apps/workspace/src/App.tsx",
        [("  }, [bearerToken, resolvedAttempt]);\n", "  }, [bearerToken]);\n")],
        ["vitest:apps/workspace/src/App.test.tsx::it says so, offers Try again and Sign out, and Try again reads it afresh"],
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
    # The live plants are in the branch's own `entra_people.py`: no diff is applied for them, and the
    # server's copy of the worktree (`stack_lease.sh remote`) is no git checkout.
    diffs = [] if only_live else DIFFS
    if (
        not only_live
        and git("status", "--porcelain", "--", "OspreyFlow_Core", "OspreyFlow_Build/tests").strip()
    ):
        print("refused: the tree has uncommitted changes")
        return 2
    for diff in diffs:
        git("apply", str(diff))
    originals: dict[str, str] = {}
    reds = missed = faults = runs = 0
    try:
        rc, tail = run_pytest([PEOPLE_LIVE] if only_live else CONTROL)
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
        for diff in reversed(diffs):
            git("apply", "-R", str(diff))
    rc, tail = run_pytest(CONTROL[:4])
    print(f"control (restored, branch alone): {'green' if rc == 0 else 'RED'} (exit {rc}) — {tail}")
    print(
        f"{len(PLANTS)} plants, {runs} case runs: {reds} red, {missed} missed, {faults} harness faults"
    )
    return 1 if missed or faults or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
