"""The model route wired into the `cloud-platform` profile (P11 part 2; ADR-135 Amendments 4 and 7,
ADR-148; the orchestrator's ruling, MORNING 37: option A, least privilege).

What a mistake would do, and the case that catches it (rule 12):
- the gateway rendered only with an engine enabled at install, so one first added in *Admin ›
  Models* has none until a re-render — `test_the_gateway_is_rendered_with_no_engine_enabled`;
- a model host allowed out with no engine enabled, now the gateway runs by default —
  `test_with_no_engine_enabled_no_model_host_is_allowed_out`;
- the gateway's pod with no identity, so Bedrock's calls are unsigned (P11 part 1's finding), or
  with the namespace's own (its S3 role), more than Bedrock needs —
  `test_the_gateway_runs_as_its_own_account_only_while_bedrock_is_enabled`;
- the gateway's role granting more than Bedrock's invoke in London (an S3 action, another region, a
  wildcard model), or trusted by another account —
  `test_the_gateway_role_grants_bedrock_invoke_in_london_alone_to_its_own_account`, each shape
  planted red (`test_the_policy_check_flags_...`);
- no Bedrock engine, yet a gateway role made — `test_without_bedrock_no_gateway_role_is_made`.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.harness.test_cloud_platform_render import AWS, _artefacts, _config, _hosts, _values
from tests.services.api.test_model_engine_kinds import BEDROCK, BEDROCK_HOST, GATEWAY, GEMINI

NETS = {**AWS, BEDROCK_HOST: ["198.18.2.0/24"], "ai-gateway.client.example": ["203.0.113.0/24"],
        "generativelanguage.googleapis.com": ["203.0.114.0/24"]}  # fmt: skip
#: The gateway's own account, as the client's platform settings name it (`secrets.irsa`).
GATEWAY_ACCOUNT = "ospreyflow-gateway"
NAMESPACE_ACCOUNT = "ospreyflow"
LONDON_MODELS = "arn:aws:bedrock:eu-west-2::foundation-model/*"
INVOKE = {"bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"}


def _engines(*providers: dict[str, Any]) -> Any:
    models = {"local_only": not providers, "sendable_handling_codes": ["P"] if providers else [],
              "providers": list(providers)}  # fmt: skip
    return _config("development", models=models, cloud_platform={"egress_nets": NETS})


def _pod(values: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((w for w in values["workloads"] if w["name"] == name), None)


def test_the_gateway_is_rendered_with_no_engine_enabled() -> None:
    values = _values(_engines())
    gateway = _pod(values, "litellm")
    assert gateway is not None, "no gateway: an engine added in Admin › Models would have none"
    # And the Conduit is told where it is, as with an engine.
    assert any(e["name"] == "LITELLM_HOST" for e in (_pod(values, "api") or {}).get("env", []))


def test_with_no_engine_enabled_no_model_host_is_allowed_out() -> None:
    """The gateway runs by default, but the namespace reaches a model host only while an engine
    is enabled: with none, the egress is the profile's `always` hosts alone."""
    assert _hosts(_values(_engines())) == AWS
    assert BEDROCK_HOST in _hosts(_values(_engines(BEDROCK)))
    assert "generativelanguage.googleapis.com" in _hosts(_values(_engines(GEMINI)))


@pytest.mark.parametrize(
    ("declared", "expected"),
    [([BEDROCK], GATEWAY_ACCOUNT), ([BEDROCK, GATEWAY], GATEWAY_ACCOUNT), ([GEMINI], None),
     ([GATEWAY], None), ([], None)],
    ids=["bedrock", "bedrock-and-gateway", "keyed", "client-gateway", "none"],
)  # fmt: skip
def test_the_gateway_runs_as_its_own_account_only_while_bedrock_is_enabled(
    declared: list[dict[str, Any]], expected: str | None
) -> None:
    values = _values(_engines(*declared))
    gateway = _pod(values, "litellm")
    assert gateway is not None
    assert gateway.get("serviceAccountName") == expected
    # Never the namespace's own account, whose role holds the buckets.
    assert gateway.get("serviceAccountName") != NAMESPACE_ACCOUNT
    for name in ("api", "worker", "report-sync"):
        pod = _pod(values, name)
        assert pod is None or pod.get("serviceAccountName") == NAMESPACE_ACCOUNT, name


# ---- the gateway's role, as the namespace's Terraform makes it ---------------------------------


def _gateway_tf(*providers: dict[str, Any]) -> str:
    return _artefacts(_engines(*providers)).get("terraform/gateway.tf", "")


def policy_faults(tf: str, account: str = GATEWAY_ACCOUNT) -> list[str]:
    """What is wrong with the gateway's Terraform, in words: anything but Bedrock's two invoke
    actions on London's foundation models, an S3 action, another region, or a trust not bound to
    the gateway's own account through the cluster's OIDC provider."""
    faults = []
    actions = set(re.findall(r'"([a-z0-9]+:[A-Za-z*]+)"', tf))
    if actions - INVOKE - {"sts:AssumeRoleWithWebIdentity"}:
        faults.append(f"actions beyond Bedrock's invoke: {sorted(actions - INVOKE)}")
    if not INVOKE <= actions:
        faults.append("Bedrock's two invoke actions are not both granted")
    if re.search(r"\bs3:", tf, re.IGNORECASE):
        faults.append("an S3 action")
    arns = set(re.findall(r'"(arn:aws:[^"]+)"', tf))
    if arns != {LONDON_MODELS}:
        faults.append(f"resources other than London's foundation models: {sorted(arns)}")
    regions = set(re.findall(r"\b[a-z]{2}(?:-gov)?-[a-z]+-[0-9]\b", tf))
    if regions - {"eu-west-2"}:
        faults.append(f"another region: {sorted(regions)}")
    subject = f'"system:serviceaccount:${{var.namespace}}:{account}"'
    if subject not in tf or tf.count("system:serviceaccount:") != 1:
        faults.append("the trust is not bound to the gateway's own account alone")
    if "var.eks_oidc_provider_arn" not in tf or '"sts.amazonaws.com"' not in tf:
        faults.append("the trust is not through the cluster's OIDC provider, for STS")
    if f'name      = "{account}"' not in tf and f'name = "{account}"' not in tf:
        faults.append("no service account of the gateway's own")
    return faults


def test_the_gateway_role_grants_bedrock_invoke_in_london_alone_to_its_own_account() -> None:
    for declared in ([BEDROCK], [BEDROCK, GATEWAY, GEMINI]):
        tf = _gateway_tf(*declared)
        assert tf, "no gateway role with a Bedrock engine enabled"
        assert policy_faults(tf) == [], policy_faults(tf)


@pytest.mark.parametrize("declared", [[], [GEMINI], [GATEWAY]], ids=["none", "keyed", "client"])
def test_without_bedrock_no_gateway_role_is_made(declared: list[dict[str, Any]]) -> None:
    assert _gateway_tf(*declared) == ""
    assert "bedrock" not in _artefacts(_engines(*declared))["terraform/irsa.tf"]


# The policy check shown red with each fault planted in the real file's own shape.


@pytest.mark.parametrize(
    ("plant", "fault"),
    [
        (lambda tf: tf.replace('"bedrock:InvokeModel",', '"bedrock:InvokeModel", "s3:GetObject",'),
         "S3"),
        (lambda tf: tf.replace("eu-west-2", "us-east-1"), "region"),
        (lambda tf: tf.replace(LONDON_MODELS, "arn:aws:bedrock:eu-west-2::*"), "London"),
        (lambda tf: tf.replace('"bedrock:InvokeModel",', '"bedrock:*",'), "invoke"),
        (lambda tf: tf.replace(GATEWAY_ACCOUNT, NAMESPACE_ACCOUNT), "own account"),
        (lambda tf: tf.replace("var.eks_oidc_provider_arn", '"*"'), "OIDC"),
    ],
    ids=["s3-action", "other-region", "any-resource", "any-action", "namespace-account", "no-oidc"],
)  # fmt: skip
def test_the_policy_check_flags_each_fault_planted(plant: Any, fault: str) -> None:
    real = _gateway_tf(BEDROCK)
    planted = plant(real)
    assert planted != real, "the plant did not change the file"
    assert policy_faults(planted), f"the check missed: {fault}"
