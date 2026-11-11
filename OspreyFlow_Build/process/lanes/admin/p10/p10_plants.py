"""P10 part 1's planted faults (CLAUDE.md rule 15): each one edits `packages/principal_auth`'s real
code at the place the behaviour lives, runs the cases that should catch it, expects them red, and
puts the file back. Run from `OspreyFlow_Core`:

    env -u OSPREY_LANE ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 \
        CLICKHOUSE_HTTP_PORT=59994 .venv/bin/python \
        ../OspreyFlow_Build/process/lanes/admin/p10/p10_plants.py

It refuses to start on a dirty `principal_auth`, restores the file in a `finally`, and runs the
whole Entra file and `test_auth.py` green before and after (the controls).

**What counts as red** (the orchestrator's review, round 1, item 1, 11 November 2026). The planted
source must compile, or the plant is a harness fault: a plant that breaks the module's syntax makes
every case fail at import and proves nothing about the branch it removed (the tenant plant did, at
`72d8719`, by replacing an 8-space `if` with a 4-space one). A case is red only when pytest exits
1 and its summary says "failed" with no "error"; any other exit (2, an interrupted or collection
error; 5, no test collected; 1 with "error", a fixture or import failure) is a harness fault, never
a red. A guard that turns a condition off keeps the matched line's own indentation (`off`).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CORE = Path.cwd()
TARGET = CORE / "packages/principal_auth/__init__.py"
TESTS = "../OspreyFlow_Build/tests/services/api/test_auth_entra_claims.py"
CONTROL = [TESTS, "../OspreyFlow_Build/tests/services/api/test_auth.py"]
E = "test_a_token_entra_would_not_accept_is_refused"
WRONG_TYPE = "test_the_default_mapping_refuses_a_claim_of_the_wrong_type"
ONE = "test_a_source_names_exactly_one_of_a_claim_or_a_group_table"
CLIENT = "test_a_token_issued_to_another_client_is_refused"
SCOPE = "test_a_token_without_this_apis_scope_is_refused"
GUEST = "test_a_guest_account_is_refused"
KC_TID = "test_an_entra_token_under_the_keycloak_handling_is_refused"


def off(line: str) -> tuple[str, str]:
    """The edit that turns one `if`/`elif` line's condition off, at that line's own indentation."""
    assert line.endswith(":\n"), line
    stripped = line.lstrip(" ")
    indent = line[: len(line) - len(stripped)]
    keyword = "elif" if stripped.startswith("elif ") else "if"
    return line, f"{indent}{keyword} False:\n"


MISSING_CLAIM = (
    "            raise PrincipalResolutionError(\n"
    '                f"token is missing required claim: {what} ({source.claim!r})"\n'
    "            )\n"
)
MISSING_GROUP = (
    "        raise PrincipalResolutionError(\n"
    '            f"token is missing required claim: no group grants the {what}"\n'
    "        )\n"
)
TENANT_CHECK = '        if claims.get("tid") != mapping.tenant_id:\n'
VERIFY_ISS = '"verify_iss": self._config.oidc_issuer is not None,'
ID_LINE = 'id=str(claims["oid"]) if mapping.is_entra else str(claims["sub"]),'

# (name, [(old text, new text), ...], test ids that must go red)
PLANTS: list[tuple[str, list[tuple[str, str]], list[str]]] = [
    (
        "two clearances or units resolved (any one picked), not refused",
        [off("    if len(found) > 1:\n")],
        [
            "test_groups_granting_two_clearances_are_refused_not_resolved",
            "test_groups_granting_two_units_are_refused",
            "test_the_owner_exchange_maps_claims_through_the_same_path",
        ],
    ),
    (
        "a missing claim-sourced value defaulted to cleared",
        [(MISSING_CLAIM, '            return "OFFICIAL-SENSITIVE"\n')],
        [
            "test_both_missing_is_refused_never_defaulted_to_cleared[extension]",
            "test_a_missing_clearance_attribute_with_the_unit_group_present_is_refused",
            "test_the_default_mapping_does_not_read_entra_attributes",
        ],
    ),
    (
        "a missing group-sourced value defaulted to cleared",
        [(MISSING_GROUP, '        return "OFFICIAL-SENSITIVE"\n')],
        [
            "test_both_missing_is_refused_never_defaulted_to_cleared[groups]",
            "test_a_missing_clearance_with_a_unit_present_is_refused",
            "test_a_missing_unit_with_a_clearance_present_is_refused",
            "test_an_unmapped_group_grants_nothing",
        ],
    ),
    (
        "an unmapped group grants a handling code",
        [("source.groups.get(g, [])", 'source.groups.get(g, ["R"])')],
        ["test_an_unmapped_group_grants_nothing"],
    ),
    (
        "a group overage (_claim_names) read as no groups",
        [("(isinstance(names, dict) and mapping.groups_claim in names)", "False")],
        ["test_a_group_overage_is_refused_not_read_as_no_groups"],
    ),
    (
        "the implicit flow's overage (hasgroups) read as no groups",
        [('or claims.get("hasgroups") is True', "or False")],
        ["test_the_implicit_flows_overage_signal_is_refused"],
    ),
    (
        "a groups claim that is not a list iterated as one",
        [
            off(
                "    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):\n"  # noqa: E501
            )
        ],
        ["test_a_groups_claim_that_is_not_a_list_of_ids_is_refused"],
    ),
    (
        "a groups list longer than Entra's cap accepted",
        [off("    if len(groups) > MAX_TOKEN_GROUPS:\n")],
        ["test_a_groups_list_past_entras_cap_is_refused"],
    ),
    (
        "a missing or other tenant's tid accepted",
        [off(TENANT_CHECK)],
        [f"{E}[other-tenant]", f"{E}[no-tid]"],
    ),
    (
        "exp not required of an Entra token",
        [('return ["sub", "exp"] if self.is_entra else ["sub"]', 'return ["sub"]')],
        [f"{E}[no-exp]"],
    ),
    (
        "the issuer not checked",
        [(VERIFY_ISS, '"verify_iss": False,')],
        [f"{E}[wrong-issuer]"],
    ),
    (
        "the audience not checked",
        [('"verify_aud": self._config.oidc_audience is not None,', '"verify_aud": False,')],
        [f"{E}[wrong-audience]"],
    ),
    (
        "the expiry not checked",
        [(VERIFY_ISS, VERIFY_ISS + ' "verify_exp": False,')],
        [f"{E}[expired]"],
    ),
    (
        "another tenant's whole token: issuer and tenant checks both removed",
        [off(TENANT_CHECK), (VERIFY_ISS, '"verify_iss": False,')],
        ["test_another_tenants_whole_token_is_refused"],
    ),
    (
        "an Entra mapping built on a resolver checking neither issuer nor audience",
        [
            (
                "        if mapping.is_entra:\n            # A tenant-bound",
                "        if False:\n            # A tenant-bound",
            )
        ],
        ["test_an_entra_mapping_without_issuer_and_audience_checks_is_refused_at_construction"],
    ),
    (
        "an Entra token's app roles read as OspreyFlow roles",
        [
            (
                'roles=[] if mapping.is_entra else _string_list(claims, CLAIM_ROLES, "roles"),',
                'roles=_string_list(claims, CLAIM_ROLES, "roles"),',
            )
        ],
        [
            "test_an_entra_app_role_grants_no_ospreyflow_role",
            "test_extension_attributes_build_the_principal",
        ],
    ),
    (
        "an Entra principal keyed by its pairwise sub (review round 1, item 3)",
        [(ID_LINE, 'id=str(claims["sub"]),')],
        [
            "test_an_entra_principal_is_keyed_by_oid_not_its_pairwise_sub",
            "test_extension_attributes_build_the_principal",
        ],
    ),
    (
        "a Keycloak principal keyed by an oid it happens to carry",
        [(ID_LINE, 'id=str(claims["oid"]) if "oid" in claims else str(claims["sub"]),')],
        ["test_a_keycloak_principal_is_still_keyed_by_sub"],
    ),
    (
        "an Entra token under the Keycloak handling accepted (review round 1, item 4)",
        [off('    elif "tid" in claims:\n')],
        [f"{KC_TID}[our-tenant]", f"{KC_TID}[other-tenant]"],
    ),
    (
        "a token issued to another client accepted (review round 1, item 8)",
        [off("        if not clients or any(c != mapping.client_id for c in clients):\n")],
        [
            f"{CLIENT}[other-azp]",
            f"{CLIENT}[no-client]",
            f"{CLIENT}[v1-other-appid]",
            f"{CLIENT}[azp-and-other-appid]",
        ],
    ),
    (
        "only azp read: a v1 token's appid ignored",
        [('for c in ("azp", "appid") if c in claims', 'for c in ("azp",) if c in claims')],
        [
            f"{CLIENT}[azp-and-other-appid]",
            "test_a_v1_token_naming_the_glass_by_appid_resolves",
        ],
    ),
    (
        "a token without this API's scope accepted",
        [off('        if mapping.scope not in scope.split(" "):\n')],
        [f"{SCOPE}[other-scope]", f"{SCOPE}[longer-name]", f"{SCOPE}[openid-only]"],
    ),
    (
        "the scope matched as a substring of scp",
        [('if mapping.scope not in scope.split(" "):', "if mapping.scope not in scope:")],
        [f"{SCOPE}[longer-name]"],
    ),
    (
        "a guest account accepted",
        [off('        if claims.get("acct") in (1, "1") or guest_idp:\n')],
        [f"{GUEST}[acct]", f"{GUEST}[acct-text]", f"{GUEST}[idp-other]"],
    ),
    (
        "a guest's acct read only as a number",
        [('claims.get("acct") in (1, "1")', 'claims.get("acct") == 1')],
        [f"{GUEST}[acct-text]"],
    ),
    (
        "an Entra mapping without the Glass's client id accepted",
        [
            (
                "        if self.tenant_id is not None and (\n"
                "            self.client_id is None or not _GUID.match(self.client_id)\n"
                "        ):\n",
                "        if False:\n",
            )
        ],
        [
            "test_an_entra_mapping_needs_the_glass_client_id[none]",
            "test_an_entra_mapping_needs_the_glass_client_id[empty]",
            "test_an_entra_mapping_needs_the_glass_client_id[not-a-guid]",
        ],
    ),
    (
        "a scope setting naming none or two",
        [off('        if not self.scope or " " in self.scope:\n')],
        [
            "test_the_scope_setting_names_one_scope[empty]",
            "test_the_scope_setting_names_one_scope[two]",
        ],
    ),
    (
        "one handling code or role, given as a string, split into its letters",
        [
            (
                "    names = [value] if isinstance(value, str) else value\n",
                "    names = list(value) if isinstance(value, str) else value\n",
            )
        ],
        [
            "test_a_single_valued_handling_code_attribute_is_one_code_not_its_letters",
            "test_the_default_mapping_reads_one_code_or_role_as_one_not_its_letters",
        ],
    ),
    (
        "handling codes or roles of the wrong type passed through",
        [
            off(
                "    if not isinstance(names, list) or not all(isinstance(v, str) for v in names):\n"  # noqa: E501
            )
        ],
        [
            "test_handling_codes_of_the_wrong_type_are_refused",
            f"{WRONG_TYPE}[object-codes]",
            f"{WRONG_TYPE}[numeric-roles]",
        ],
    ),
    (
        "an empty handling code accepted (review round 1, item 9)",
        [off("    if not all(names):\n")],
        [
            "test_an_empty_handling_code_is_refused[empty-string]",
            "test_an_empty_handling_code_is_refused[empty-in-list]",
        ],
    ),
    (
        "a handling code given twice kept twice",
        [("    return list(dict.fromkeys(names))\n", "    return list(names)\n")],
        ["test_a_handling_code_given_twice_is_kept_once"],
    ),
    (
        "one clearance or unit group granting a list of values",
        [
            (
                "    groups: dict[str, str] | None = None\n",
                "    groups: dict[str, str | list[str]] | None = None\n",
            )
        ],
        [
            "test_one_group_cannot_grant_two_clearances_or_units[clearance]",
            "test_one_group_cannot_grant_two_clearances_or_units[org_unit]",
        ],
    ),
    (
        "a list, number or empty clearance accepted as a value (str()-ed)",
        [
            off("        if not isinstance(value, str) or not value:\n"),
            ("        return value\n    assert", "        return str(value)\n    assert"),
        ],
        [
            "test_an_empty_clearance_attribute_is_refused",
            "test_a_clearance_attribute_that_is_not_a_string_is_refused",
            "test_a_numeric_clearance_attribute_is_refused_not_turned_into_text",
            f"{WRONG_TYPE}[list-clearance]",
            f"{WRONG_TYPE}[empty-clearance]",
            f"{WRONG_TYPE}[numeric-unit]",
        ],
    ),
    (
        "an oid that is not an Entra object id accepted",
        [
            off(
                '        if not isinstance(claims.get("oid"), str) or not _GUID.match(claims["oid"]):\n'  # noqa: E501
            )
        ],
        ["test_an_oid_that_is_not_an_object_id_is_refused", f"{E}[no-oid]"],
    ),
    (
        "an app-only token accepted as a person",
        [
            off(
                '        if claims.get("idtyp") == "app" or not isinstance(scope, str) or not scope:\n'  # noqa: E501
            )
        ],
        [
            "test_an_app_only_token_is_no_person[app-token]",
            "test_an_app_only_token_is_no_person[no-scp]",
            "test_an_app_only_token_is_no_person[idtyp-app]",
        ],
    ),
    (
        "both a missing claim and a missing group defaulted (the mixed mapping)",
        [
            (MISSING_CLAIM, '            return "OFFICIAL-SENSITIVE"\n'),
            (MISSING_GROUP, '        return "unit-1"\n'),
        ],
        ["test_both_missing_is_refused_never_defaulted_to_cleared[mixed]"],
    ),
    (
        "a source naming both a claim and a group table, or neither",
        [off("        if (self.claim is None) == (groups is None):\n")],
        [f"{ONE}[neither]", f"{ONE}[both]"],
    ),
    (
        "an empty claim name accepted",
        [off("        if self.claim is not None and not self.claim:\n")],
        [f"{ONE}[empty-claim]"],
    ),
    (
        "an empty group table accepted",
        [off("            if not groups:\n")],
        [f"{ONE}[empty-table]"],
    ),
    (
        "a group table entry granting an empty value accepted",
        [off("                if not values or not all(values):\n")],
        ["test_a_group_table_entry_must_grant_a_value[empty-value]"],
    ),
    (
        "a group table key that is not a group id accepted",
        [off("                if not _GUID.match(group):\n")],
        [
            "test_a_group_table_key_must_be_a_group_id",
            "test_a_group_table_entry_must_grant_a_value[empty-group]",
        ],
    ),
    (
        "an unnamed groups claim accepted",
        [off("        if not self.groups_claim:\n")],
        ["test_the_groups_claim_must_be_named"],
    ),
    (
        "the resolver trusts a mapping that skipped its validators",
        [
            (
                "        mapping = ClaimMapping.model_validate(\n"
                '            (claim_mapping or DEFAULT_CLAIM_MAPPING).model_dump(mode="python")\n'
                "        )\n",
                "        mapping = claim_mapping or DEFAULT_CLAIM_MAPPING\n",
            )
        ],
        [
            "test_a_mapping_that_skipped_its_validators_is_validated_by_the_resolver[copy]",
            "test_a_mapping_that_skipped_its_validators_is_validated_by_the_resolver[construct]",
        ],
    ),
    (
        "an Entra mapping without a tenant accepted",
        [off("        if not fixed and self.tenant_id is None:\n")],
        ["test_a_mapping_other_than_the_fixed_names_needs_its_tenant"],
    ),
    (
        "a tenant id that is not a GUID accepted",
        [off("        if self.tenant_id is not None and not _GUID.match(self.tenant_id):\n")],
        [
            "test_the_tenant_id_must_be_a_guid[empty]",
            "test_the_tenant_id_must_be_a_guid[name]",
            "test_the_tenant_id_must_be_a_guid[bad]",
        ],
    ),
    (
        "a misspelt setting ignored",
        [
            (
                '    model_config = ConfigDict(frozen=True, extra="forbid")\n\n    clearance:',
                '    model_config = ConfigDict(frozen=True, extra="ignore")\n\n    clearance:',
            )
        ],
        ["test_the_settings_refuse_an_unknown_key"],
    ),
    (
        "the default mapping's clearance name changed",
        [('CLAIM_CLEARANCE = "clearance"\n', 'CLAIM_CLEARANCE = "clearance_level"\n')],
        ["test_the_default_mapping_is_the_fixed_claim_names"],
    ),
    (
        "the exchange path maps by the fixed names, not the deployment's mapping",
        [
            (
                "            return self.resolve(exchanged_token)\n",
                "            return principal_from_claims(\n"
                '                jwt.decode(exchanged_token, options={"verify_signature": False}),\n'  # noqa: E501
                "                DEFAULT_CLAIM_MAPPING,\n"
                "            )\n",
            )
        ],
        ["test_the_owner_exchange_maps_claims_through_the_same_path"],
    ),
    (
        "a second Principal construction in principal_auth",
        [
            (
                "DEFAULT_CLAIM_MAPPING = ClaimMapping()\n",
                "DEFAULT_CLAIM_MAPPING = ClaimMapping()\n\n\n"
                "def _second_path(claims: Mapping[str, Any]) -> Principal:\n"
                '    return Principal(id="x", clearance="x", org_unit="x")\n',
            )
        ],
        ["test_one_principal_construction_in_principal_auth"],
    ),
]


def run(nodeids: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
         "no:cacheprovider", *nodeids],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-300:]
    return proc.returncode, tail


def verdict(rc: int, tail: str) -> str:
    """`red`, `MISSED` or `HARNESS FAULT`: only exit 1 with "failed" and no "error" is a red."""
    if rc == 0:
        return "MISSED"
    if rc == 1 and "failed" in tail and "error" not in tail:
        return "red"
    return "HARNESS FAULT"


def self_test() -> int:
    """The harness's own red (rule 15): the shapes that fooled it at `72d8719` are each a fault."""
    checks = {
        "an import error ('1 error') is a fault": verdict(1, "1 error in 0.63s") == "HARNESS FAULT",
        "a failure with an error is a fault": verdict(1, "1 failed, 1 error in 1s")
        == "HARNESS FAULT",
        "exit 2 is a fault": verdict(2, "1 failed in 1s") == "HARNESS FAULT",
        "exit 5 (nothing collected) is a fault": verdict(5, "no tests ran in 0.1s")
        == "HARNESS FAULT",
        "exit 0 is a miss": verdict(0, "1 passed in 1s") == "MISSED",
        "exit 1 with 'failed' is a red": verdict(1, "1 failed in 1.6s") == "red",
        "off keeps the 8-space indentation": off(TENANT_CHECK)[1] == "        if False:\n",
        "off keeps elif": off('    elif "tid" in claims:\n')[1] == "    elif False:\n",
    }
    original = TARGET.read_text()
    old_plant = original.replace(TENANT_CHECK, "    if False:\n")  # the 72d8719 plant, as it was
    try:
        compile(old_plant, str(TARGET), "exec")
        checks["the 72d8719 tenant plant fails to compile"] = False
    except SyntaxError:
        checks["the 72d8719 tenant plant fails to compile"] = True
    new_plant = original.replace(*off(TENANT_CHECK))
    compile(new_plant, str(TARGET), "exec")
    for name, ok in checks.items():
        print(f"self-test: {'ok' if ok else 'FAILED'} — {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    status = subprocess.run(
        ["git", "status", "--porcelain", str(TARGET)], capture_output=True, text=True, check=True
    ).stdout
    if status.strip():
        print(f"refused: {TARGET} has uncommitted changes")
        return 2
    original = TARGET.read_text()
    rc, tail = run(CONTROL)
    print(f"control (no plant): {'green' if rc == 0 else 'RED'} (exit {rc}) — {tail}")
    if rc != 0:
        return 1
    reds = missed = faults = runs = 0
    try:
        for name, edits, ids in PLANTS:
            planted = original
            for old, new in edits:
                if planted.count(old) != 1:
                    print(f"HARNESS FAULT, plant misses its site ({planted.count(old)}): {name}")
                    faults += 1
                    break
                planted = planted.replace(old, new)
            else:
                try:
                    compile(planted, str(TARGET), "exec")
                except SyntaxError as exc:
                    print(f"HARNESS FAULT, planted source does not compile ({exc}): {name}")
                    faults += 1
                    continue
                TARGET.write_text(planted)
                for test_id in ids:
                    rc, tail = run([f"{TESTS}::{test_id}"])
                    result = verdict(rc, tail)
                    runs += 1
                    reds += result == "red"
                    missed += result == "MISSED"
                    faults += result == "HARNESS FAULT"
                    print(f"[{name}] {test_id}: {result} (exit {rc}) — {tail}")
                TARGET.write_text(original)
    finally:
        TARGET.write_text(original)
    rc, tail = run(CONTROL)
    print(f"control (restored): {'green' if rc == 0 else 'RED'} (exit {rc}) — {tail}")
    print(
        f"{len(PLANTS)} plants, {runs} case runs: {reds} red, {missed} missed, "
        f"{faults} harness faults"
    )
    return 1 if missed or faults or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
