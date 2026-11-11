"""P10 part 1's planted faults (CLAUDE.md rule 15): each one edits `packages/principal_auth`'s real
code at the place the behaviour lives, runs the cases that should catch it, expects them red, and
puts the file back. Run from `OspreyFlow_Core`:

    env -u OSPREY_LANE ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 \
        CLICKHOUSE_HTTP_PORT=59994 .venv/bin/python \
        ../OspreyFlow_Build/process/lanes/admin/p10/p10_plants.py

It refuses to start on a dirty `principal_auth`, restores the file in a `finally`, and runs the
whole Entra file and `test_auth.py` green before and after (the controls).
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

# (name, [(old text, new text), ...], test ids that must go red)
PLANTS: list[tuple[str, list[tuple[str, str]], list[str]]] = [
    (
        "two clearances or units resolved (any one picked), not refused",
        [("    if len(found) > 1:\n", "    if False:\n")],
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
            (
                "    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):\n",  # noqa: E501
                "    if False:\n",
            )
        ],
        ["test_a_groups_claim_that_is_not_a_list_of_ids_is_refused"],
    ),
    (
        "a missing or other tenant's tid accepted",
        [(TENANT_CHECK, "    if False:\n")],
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
        [(TENANT_CHECK, "    if False:\n"), (VERIFY_ISS, '"verify_iss": False,')],
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
        "one handling code or role, given as a string, split into its letters",
        [("        return [value] if value else []\n", "        return list(value)\n")],
        [
            "test_a_single_valued_handling_code_attribute_is_one_code_not_its_letters",
            "test_the_default_mapping_reads_one_code_or_role_as_one_not_its_letters",
        ],
    ),
    (
        "handling codes or roles of the wrong type passed through",
        [
            (
                "    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):\n",  # noqa: E501
                "    if False:\n",
            )
        ],
        [
            "test_handling_codes_of_the_wrong_type_are_refused",
            f"{WRONG_TYPE}[object-codes]",
            f"{WRONG_TYPE}[numeric-roles]",
        ],
    ),
    (
        "a list, number or empty clearance accepted as a value (str()-ed)",
        [
            (
                "        if not isinstance(value, str) or not value:\n",
                "        if False:\n",
            ),
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
            (
                '        if not isinstance(claims.get("oid"), str) or not _GUID.match(claims["oid"]):\n',  # noqa: E501
                "        if False:\n",
            )
        ],
        ["test_an_oid_that_is_not_an_object_id_is_refused", f"{E}[no-oid]"],
    ),
    (
        "an app-only token accepted as a person",
        [
            (
                '        if claims.get("idtyp") == "app" or not isinstance(scope, str) or not scope:\n',  # noqa: E501
                "        if False:\n",
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
        [("        if (self.claim is None) == (groups is None):\n", "        if False:\n")],
        [f"{ONE}[neither]", f"{ONE}[both]"],
    ),
    (
        "an empty claim name accepted",
        [("        if self.claim is not None and not self.claim:\n", "        if False:\n")],
        [f"{ONE}[empty-claim]"],
    ),
    (
        "an empty group table accepted",
        [("            if not groups:\n", "            if False:\n")],
        [f"{ONE}[empty-table]"],
    ),
    (
        "a group table entry granting an empty value accepted",
        [("                if not values or not all(values):\n", "                if False:\n")],
        ["test_a_group_table_entry_must_grant_a_value[empty-value]"],
    ),
    (
        "a group table key that is not a group id accepted",
        [("                if not _GUID.match(group):\n", "                if False:\n")],
        [
            "test_a_group_table_key_must_be_a_group_id",
            "test_a_group_table_entry_must_grant_a_value[empty-group]",
        ],
    ),
    (
        "an unnamed groups claim accepted",
        [("        if not self.groups_claim:\n", "        if False:\n")],
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
        [("        if not fixed and self.tenant_id is None:\n", "        if False:\n")],
        ["test_a_mapping_other_than_the_fixed_names_needs_its_tenant"],
    ),
    (
        "a tenant id that is not a GUID accepted",
        [
            (
                "        if self.tenant_id is not None and not _GUID.match(self.tenant_id):\n",
                "        if False:\n",
            )
        ],
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


def run(nodeids: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
         "no:cacheprovider", *nodeids],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-300:]
    return proc.returncode == 0, tail


def main() -> int:
    status = subprocess.run(
        ["git", "status", "--porcelain", str(TARGET)], capture_output=True, text=True, check=True
    ).stdout
    if status.strip():
        print(f"refused: {TARGET} has uncommitted changes")
        return 2
    original = TARGET.read_text()
    ok, tail = run(CONTROL)
    print(f"control (no plant): {'green' if ok else 'RED'} — {tail}")
    if not ok:
        return 1
    failures = 0
    try:
        for name, edits, ids in PLANTS:
            planted = original
            for old, new in edits:
                if planted.count(old) != 1:
                    print(f"PLANT MISSES its site ({planted.count(old)} matches): {name}")
                    failures += 1
                    break
                planted = planted.replace(old, new)
            else:
                TARGET.write_text(planted)
                for test_id in ids:
                    passed, tail = run([f"{TESTS}::{test_id}"])
                    failures += passed
                    verdict = "red (caught)" if not passed else "GREEN (MISSED)"
                    print(f"[{name}] {test_id}: {verdict} — {tail}")
                TARGET.write_text(original)
    finally:
        TARGET.write_text(original)
    ok, tail = run(CONTROL)
    print(f"control (restored): {'green' if ok else 'RED'} — {tail}")
    print(f"{len(PLANTS)} plants, {failures} missed")
    return 1 if failures or not ok else 0


if __name__ == "__main__":
    sys.exit(main())
