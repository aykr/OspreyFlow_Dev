"""P10 part 1's planted faults (CLAUDE.md rule 15): each one edits `packages/principal_auth`'s real
code at the place the behaviour lives, runs the cases that should catch it, expects them red, and
puts the file back. Run from `OspreyFlow_Core`:

    env -u OSPREY_LANE ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 \
        CLICKHOUSE_HTTP_PORT=59994 .venv/bin/python ../OspreyFlow_Build/process/lanes/admin/p10/p10_plants.py

It refuses to start on a dirty `principal_auth`, and restores the file in a `finally`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CORE = Path.cwd()
TARGET = CORE / "packages/principal_auth/__init__.py"
TESTS = "../OspreyFlow_Build/tests/services/api/test_auth_entra_claims.py"

# (name, old text, new text, test ids that must go red)
PLANTS: list[tuple[str, str, str, list[str]]] = [
    (
        "two clearances or units resolved (any one picked), not refused",
        "    if len(found) > 1:\n",
        "    if False:\n",
        [
            "test_groups_granting_two_clearances_are_refused_not_resolved",
            "test_groups_granting_two_units_are_refused",
            "test_the_owner_exchange_maps_claims_through_the_same_path",
        ],
    ),
    (
        "a missing claim-sourced value defaulted to cleared",
        '            raise PrincipalResolutionError(\n                f"token is missing required claim: {what} ({source.claim!r})"\n            )\n',
        '            return "OFFICIAL-SENSITIVE"\n',
        [
            "test_both_missing_is_refused_never_defaulted_to_cleared[extension]",
            "test_both_missing_is_refused_never_defaulted_to_cleared[mixed]",
            "test_the_default_mapping_does_not_read_entra_attributes",
        ],
    ),
    (
        "a missing group-sourced value defaulted to cleared",
        '        raise PrincipalResolutionError(f"token is missing required claim: no group grants a {what}")\n',
        '        return "OFFICIAL-SENSITIVE"\n',
        [
            "test_both_missing_is_refused_never_defaulted_to_cleared[groups]",
            "test_a_missing_clearance_with_a_unit_present_is_refused",
            "test_a_missing_unit_with_a_clearance_present_is_refused",
            "test_an_unmapped_group_grants_nothing",
        ],
    ),
    (
        "an unmapped group grants a handling code",
        "        for code in source.groups.get(g, []):\n",
        '        for code in source.groups.get(g, ["R"]):\n',
        ["test_an_unmapped_group_grants_nothing"],
    ),
    (
        "a group overage read as no groups",
        "        and mapping.groups_claim in names\n",
        "        and False\n",
        ["test_a_group_overage_is_refused_not_read_as_no_groups"],
    ),
    (
        "a groups claim that is not a list iterated as one",
        "    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):\n",
        "    if False:\n",
        ["test_a_groups_claim_that_is_not_a_list_of_ids_is_refused"],
    ),
    (
        "another tenant's tid accepted",
        '    if mapping.tenant_id is not None and claims.get("tid") != mapping.tenant_id:\n',
        "    if False:\n",
        ["test_a_token_entra_would_not_accept_is_refused[other-tenant]"],
    ),
    (
        "oid, tid and exp not required of an Entra token",
        '        return ["sub", "exp", "oid", "tid"] if self.tenant_id else ["sub"]\n',
        '        return ["sub"]\n',
        [
            "test_a_token_entra_would_not_accept_is_refused[no-oid]",
            "test_a_token_entra_would_not_accept_is_refused[no-tid]",
            "test_a_token_entra_would_not_accept_is_refused[no-exp]",
        ],
    ),
    (
        "an Entra mapping built on a resolver checking neither issuer nor audience",
        "        if mapping.tenant_id is not None:\n            # A tenant-bound",
        "        if False:\n            # A tenant-bound",
        ["test_an_entra_mapping_without_issuer_and_audience_checks_is_refused_at_construction"],
    ),
    (
        "a single-valued handling code split into its letters",
        "            return [value] if value else []\n",
        "            return list(value)\n",
        ["test_a_single_valued_handling_code_attribute_is_one_code_not_its_letters"],
    ),
    (
        "handling codes of the wrong type passed through",
        "        if not isinstance(value, list) or not all(isinstance(c, str) for c in value):\n",
        "        if False:\n",
        ["test_handling_codes_of_the_wrong_type_are_refused"],
    ),
    (
        "a list or empty clearance accepted as a value",
        '        if isinstance(value, (list, dict, bool)) or value == "":\n',
        "        if False:\n",
        [
            "test_an_empty_clearance_attribute_is_refused",
            "test_a_clearance_attribute_that_is_not_a_string_is_refused",
        ],
    ),
    (
        "a source naming both a claim and a group table, or neither",
        "        if (self.claim is None) == (groups is None):\n",
        "        if False:\n",
        [
            "test_a_source_names_exactly_one_of_a_claim_or_a_group_table[neither]",
            "test_a_source_names_exactly_one_of_a_claim_or_a_group_table[both]",
        ],
    ),
    (
        "a misspelt setting ignored",
        '    model_config = ConfigDict(frozen=True, extra="forbid")\n\n    clearance:',
        '    model_config = ConfigDict(frozen=True, extra="ignore")\n\n    clearance:',
        ["test_the_settings_refuse_an_unknown_key"],
    ),
    (
        "the exchange path builds its principal by a second path (fixed names)",
        "            return self.resolve(exchanged_token)\n",
        "            return principal_from_claims(\n"
        '                jwt.decode(exchanged_token, options={"verify_signature": False}),\n'
        "                DEFAULT_CLAIM_MAPPING,\n"
        "            )\n",
        ["test_the_owner_exchange_maps_claims_through_the_same_path"],
    ),
    (
        "a second Principal construction in principal_auth",
        "DEFAULT_CLAIM_MAPPING = ClaimMapping()\n",
        "DEFAULT_CLAIM_MAPPING = ClaimMapping()\n\n\n"
        "def _second_path(claims: Mapping[str, Any]) -> Principal:\n"
        '    return Principal(id="x", clearance="x", org_unit="x")\n',
        ["test_one_principal_construction_in_principal_auth"],
    ),
]


def run(ids: list[str]) -> tuple[bool, str]:
    nodeids = [f"{TESTS}::{i}" for i in ids]
    proc = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p", "no:cacheprovider",
         *nodeids],
        capture_output=True, text=True, check=False,
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-300:]
    return proc.returncode == 0, tail


def main() -> int:
    status = subprocess.run(["git", "status", "--porcelain", str(TARGET)], capture_output=True,
                            text=True, check=True).stdout
    if status.strip():
        print(f"refused: {TARGET} has uncommitted changes")
        return 2
    original = TARGET.read_text()
    all_ids = sorted({i for *_, ids in PLANTS for i in ids})
    ok, tail = run(all_ids)
    print(f"control (no plant): {'green' if ok else 'RED'} — {tail}")
    if not ok:
        return 1
    failures = 0
    try:
        for name, old, new, ids in PLANTS:
            if original.count(old) != 1:
                print(f"PLANT MISSES its site ({original.count(old)} matches): {name}")
                failures += 1
                continue
            TARGET.write_text(original.replace(old, new))
            for test_id in ids:
                passed, tail = run([test_id])
                verdict = "red (caught)" if not passed else "GREEN (MISSED)"
                failures += passed
                print(f"[{name}] {test_id}: {verdict} — {tail}")
            TARGET.write_text(original)
    finally:
        TARGET.write_text(original)
    ok, tail = run(all_ids)
    print(f"control (restored): {'green' if ok else 'RED'} — {tail}")
    print(f"{len(PLANTS)} plants, {failures} missed")
    return 1 if failures or not ok else 0


if __name__ == "__main__":
    sys.exit(main())
