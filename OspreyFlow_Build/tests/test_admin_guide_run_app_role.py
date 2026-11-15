"""The administration guide's §6a.7 on the run API's app role as the code has it (ADR-148
Amendment 20, v0.6.0 #18; rule 12).

- The refusal the guide quotes is the Conduit's own words.
- The role it names is `principal_auth`'s, and the poc manifest's API registration lists it.
- `ospreyflow run`'s scope on Entra ID (`OSPREY_TOKEN_SCOPE`) is said where the guide says how
  it signs in.

Each is read from the code, so a change of words or name in one place and not the other fails
here. The guide's first draft, which sent an administrator to the wrong Entra blade, is refused.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
GUIDE = CORE / "docs" / "administration-guide.md"
#: The first draft's words, which named the API's own registration (App roles), not the
#: orchestrator's.
OLD_WORDS = (
    "assign it to the application (the API's registration, App roles), then sign in again"
)
CONTROL = re.compile(
    r"<!-- document-control:begin -->.*?<!-- document-control:end -->", re.DOTALL
)
SCOPE = (
    "`OSPREY_TOKEN_SCOPE` set to the API's own scope, its application ID URI followed by "
    "`/.default`"
)


def guide() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", CONTROL.sub(" ", text))


def test_the_guide_quotes_the_run_apis_own_refusal() -> None:
    from services.api.service_identity import RUN_ROLE_NOT_HELD

    assert f'"{RUN_ROLE_NOT_HELD}"' in guide()


def test_the_guide_and_the_manifest_name_principal_auths_role() -> None:
    from principal_auth import RUN_APP_ROLE

    assert f"app role `{RUN_APP_ROLE}`" in guide()
    manifest_path = CORE / "harness/cloud_platform/poc_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert RUN_APP_ROLE in manifest["entra"]["api"]["app_roles"]


def test_the_first_drafts_wrong_blade_is_gone() -> None:
    assert OLD_WORDS not in guide()


def test_the_guide_says_the_cli_sends_the_apis_scope_on_entra() -> None:
    """`ospreyflow run` on Entra ID needs `OSPREY_TOKEN_SCOPE` (the CLI's `service_token`): the
    guide's §6a.7 and its `run` row in §8 say so."""
    assert SCOPE in guide()
    rows = GUIDE.read_text(encoding="utf-8").splitlines()
    run_row = next(line for line in rows if line.startswith("| `ospreyflow run "))
    assert "`OSPREY_TOKEN_SCOPE`" in run_row
