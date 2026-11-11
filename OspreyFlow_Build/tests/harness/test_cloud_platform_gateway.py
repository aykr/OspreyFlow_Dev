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

from tests.harness.test_cloud_platform_render import AWS, _artefacts, _hosts, _values
from tests.services.api.test_model_engine_kinds import (
    BEDROCK,
    BEDROCK_HOST,
    GATEWAY,
    GEMINI,
    _cloud_config,
)

#: The gateway's own account, as the client's platform settings name it (`secrets.irsa`).
GATEWAY_ACCOUNT = "ospreyflow-gateway"
NAMESPACE_ACCOUNT = "ospreyflow"
LONDON_MODELS = "arn:aws:bedrock:eu-west-2::foundation-model/*"
INVOKE = {"bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"}


def _engines(*providers: dict[str, Any]) -> Any:
    """A real cloud-platform deployment with these engines, each host given its networks (one
    helper, the engine kinds' own)."""
    return _cloud_config(*providers)


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


Item = tuple[str, str, Any]  # ("attr", name, value) or ("block", header, [items])


def parse_hcl(text: str) -> list[Item]:
    """The rendered Terraform as `terraform._hcl` writes it: blocks (`header {`), maps
    (`name = {`) and attributes (`name = value`), one to a line. Enough to compare the gateway's
    file block by block, never by searching its text (the orchestrator's round 1, item 3)."""
    lines = [x.strip() for x in text.splitlines()]
    lines = [x for x in lines if x and not x.startswith("#")]

    def items(i: int) -> tuple[list[Item], int]:
        found: list[Item] = []
        while i < len(lines):
            line = lines[i]
            if line == "}":
                return found, i + 1
            if line.endswith("{"):
                head = line[:-1].strip()
                body, i = items(i + 1)
                kind = "map" if head.endswith("=") else "block"
                found.append((kind, head.rstrip("= ").strip(), body))
                continue
            name, _, value = line.partition("=")
            found.append(("attr", name.strip(), value.strip()))
            i += 1
        return found, i

    return items(0)[0]


def _only(body: list[Item], expected: dict[str, str]) -> list[str]:
    """Faults where `body`'s attributes and blocks are not exactly `expected` (name → value)."""
    seen = {name: value for kind, name, value in body if kind == "attr"}
    faults = [f"unexpected {kind} {name!r}" for kind, name, _ in body
              if kind != "attr" or name not in expected]  # fmt: skip
    faults += [f"{name} is {seen.get(name)!r}, not {want!r}"
               for name, want in expected.items() if seen.get(name) != want]  # fmt: skip
    return faults


def policy_faults(tf: str, account: str = GATEWAY_ACCOUNT) -> list[str]:
    """What is wrong with the gateway's Terraform, in words, compared block by block: exactly the
    six blocks; one permissions statement holding exactly Bedrock's two invoke actions on London's
    foundation models (no effect, no `not_*`, no condition, no principal); one trust statement,
    `sts:AssumeRoleWithWebIdentity` by the cluster's OIDC provider alone, with exactly two
    `StringEquals` conditions pinning `:sub` to the gateway's own account and `:aud` to STS."""
    blocks = {name: body for kind, name, body in parse_hcl(tf) if kind == "block"}
    expected = {
        'data "aws_iam_policy_document" "gateway_bedrock"',
        'resource "aws_iam_policy" "gateway_bedrock"',
        'data "aws_iam_policy_document" "gateway_trust"',
        'resource "aws_iam_role" "gateway"',
        'resource "aws_iam_role_policy_attachment" "gateway_bedrock"',
        'resource "kubernetes_service_account" "gateway"',
    }
    faults = [f"unexpected block {name!r}" for name in set(blocks) - expected]
    faults += [f"missing block {name!r}" for name in expected - set(blocks)]
    if faults:
        return faults
    grant = blocks['data "aws_iam_policy_document" "gateway_bedrock"']
    if [(k, n) for k, n, _ in grant] != [("block", "statement")]:
        faults.append("the permissions document is not exactly one statement")
    else:
        faults += _only(grant[0][2], {
            "actions": '["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]',
            "resources": f'["{LONDON_MODELS}"]',
        })  # fmt: skip
    trust = blocks['data "aws_iam_policy_document" "gateway_trust"']
    if [(k, n) for k, n, _ in trust] != [("block", "statement")]:
        faults.append("the trust document is not exactly one statement")
    else:
        statement = trust[0][2]
        principals = [b for k, n, b in statement if k == "block" and n == "principals"]
        conditions = [b for k, n, b in statement if k == "block" and n == "condition"]
        others = [n for k, n, _ in statement if (k, n) not in {
            ("attr", "actions"), ("block", "principals"), ("block", "condition")}]  # fmt: skip
        faults += [f"unexpected {n!r} in the trust" for n in others]
        actions = next((v for k, n, v in statement if k == "attr" and n == "actions"), None)
        if actions != '["sts:AssumeRoleWithWebIdentity"]':
            faults.append(f"the trust's actions are {actions!r}")
        if len(principals) != 1:
            faults.append(f"{len(principals)} principals in the trust, not one")
        else:
            faults += _only(principals[0], {
                "type": '"Federated"', "identifiers": "[var.eks_oidc_provider_arn]"})  # fmt: skip
        subject = f'["system:serviceaccount:${{var.namespace}}:{account}"]'
        pinned = {
            '"${var.eks_oidc_issuer}:sub"': subject,
            '"${var.eks_oidc_issuer}:aud"': '["sts.amazonaws.com"]',
        }
        variables = sorted(dict((n, v) for k, n, v in c if k == "attr").get("variable", "")
                           for c in conditions)  # fmt: skip
        if variables != sorted(pinned):
            faults.append(f"the trust's conditions are on {variables}, not :sub and :aud")
        for condition in conditions:
            variable = dict((n, v) for k, n, v in condition if k == "attr").get("variable", "")
            faults += _only(condition, {"test": '"StringEquals"', "variable": variable,
                                        "values": pinned.get(variable, "?")})  # fmt: skip
    faults += _only(blocks['resource "aws_iam_role" "gateway"'], {
        "name": '"${var.namespace}-gateway"',
        "assume_role_policy": "data.aws_iam_policy_document.gateway_trust.json"})  # fmt: skip
    faults += _only(blocks['resource "aws_iam_policy" "gateway_bedrock"'], {
        "name": '"${var.namespace}-gateway-bedrock"',
        "policy": "data.aws_iam_policy_document.gateway_bedrock.json"})  # fmt: skip
    faults += _only(blocks['resource "aws_iam_role_policy_attachment" "gateway_bedrock"'], {
        "role": "aws_iam_role.gateway.name",
        "policy_arn": "aws_iam_policy.gateway_bedrock.arn"})  # fmt: skip
    account_block = blocks['resource "kubernetes_service_account" "gateway"']
    metadata = next((b for k, n, b in account_block if n == "metadata"), [])
    faults += _only(account_block, {}) if [n for _, n, _ in account_block] != ["metadata"] else []
    annotations = next((b for k, n, b in metadata if k == "map" and n == "annotations"), [])
    if dict((n, v) for k, n, v in metadata if k == "attr") != {
        "name": f'"{account}"', "namespace": "var.namespace"}:  # fmt: skip
        faults.append("the service account is not the gateway's own, in the namespace")
    if [(n, v) for _, n, v in annotations] != [
        ('"eks.amazonaws.com/role-arn"', "aws_iam_role.gateway.arn")]:  # fmt: skip
        faults.append("the service account is not annotated with the gateway's role alone")
    return faults


def stray_gateway_references(
    artefacts: dict[str, str], account: str = GATEWAY_ACCOUNT
) -> list[str]:
    """Each rendered Terraform file but `gateway.tf` that names the gateway's role, its policy or
    its account: an attachment or a trust elsewhere would widen what the role may do, or who may
    take it, unseen by the check of `gateway.tf` alone (the orchestrator's round 2, item 3)."""
    names = ("aws_iam_role.gateway", "gateway_bedrock", "gateway_trust", f'"{account}"',
             f":{account}\"")  # fmt: skip
    return [
        f"{path} names {name}"
        for path, text in sorted(artefacts.items())
        if path.startswith("terraform/") and path != "terraform/gateway.tf"
        for name in names
        if name in text
    ]


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


STATEMENT = (
    "  statement {\n"
    '    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]\n'
)
ACTIONS = '["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]'
SUB_TEST = '      test     = "StringEquals"\n      variable = "${var.eks_oidc_issuer}:sub"'


@pytest.mark.parametrize(
    ("plant", "fault"),
    [
        (lambda tf: tf.replace(ACTIONS, ACTIONS[:-1] + ', "s3:GetObject"]'), "an S3 action"),
        (lambda tf: tf.replace(ACTIONS, ACTIONS[:-1] + ', "*"]'), "a bare * action"),
        (lambda tf: tf.replace(ACTIONS, '["bedrock:*"]'), "any Bedrock action"),
        (lambda tf: tf.replace(ACTIONS, ACTIONS[:-1] + ', "aws-marketplace:Subscribe"]'),
         "a hyphenated service's action"),
        (lambda tf: tf.replace(ACTIONS, ACTIONS[:-1] + ', "IAM:PassRole"]'), "a capitalised one"),
        (lambda tf: tf.replace(f'["{LONDON_MODELS}"]', f'["{LONDON_MODELS}", "*"]'),
         "a bare * resource"),
        (lambda tf: tf.replace("eu-west-2", "us-east-1"), "another region"),
        (lambda tf: tf.replace(LONDON_MODELS, "arn:aws:bedrock:eu-west-2::*"), "any resource"),
        (lambda tf: tf.replace("    actions   =", "    not_actions =", 1), "not_actions"),
        (lambda tf: tf.replace("    resources =", "    not_resources =", 1), "not_resources"),
        (lambda tf: tf.replace(STATEMENT, '  statement {\n    effect = "Deny"\n'
                               + STATEMENT.split("\n", 1)[1], 1), "a Deny"),
        (lambda tf: tf.replace(STATEMENT, '  statement {\n    actions = ["*"]\n'
                               '    resources = ["*"]\n  }\n\n' + STATEMENT, 1),
         "a whole */* statement"),
        (lambda tf: tf.replace(SUB_TEST, SUB_TEST.replace("StringEquals", "StringLike")),
         "StringLike"),
        (lambda tf: tf.replace(SUB_TEST, SUB_TEST.replace("StringEquals", "StringNotEquals")),
         "StringNotEquals"),
        (lambda tf: tf.replace("[var.eks_oidc_provider_arn]", '[var.eks_oidc_provider_arn, "*"]'),
         "an extra principal *"),
        (lambda tf: tf.replace("var.eks_oidc_provider_arn", '"*"'), "no OIDC"),
        (lambda tf: tf.replace(GATEWAY_ACCOUNT, NAMESPACE_ACCOUNT), "the namespace's account"),
        (lambda tf: tf.replace(
            'data "aws_iam_policy_document" "gateway_trust" {\n',
            'data "aws_iam_policy_document" "gateway_trust" {\n  statement {\n'
            '    actions = ["sts:AssumeRoleWithWebIdentity"]\n  }\n\n'),
         "a second trust statement"),
    ],
    ids=["s3-action", "star-action", "bedrock-star", "marketplace", "capital", "star-resource",
         "other-region", "any-resource", "not-actions", "not-resources", "deny", "star-statement",
         "string-like", "string-not-equals", "star-principal", "no-oidc", "namespace-account",
         "second-trust"],
)  # fmt: skip
def test_the_policy_check_flags_each_fault_planted(plant: Any, fault: str) -> None:
    real = _gateway_tf(BEDROCK)
    assert policy_faults(real) == []
    planted = plant(real)
    assert planted != real, f"the plant did not change the file: {fault}"
    assert policy_faults(planted), f"the check missed: {fault}"


# ---- the two accounts kept apart (the orchestrator's round 1, items 5 and 6) -------------------


def test_with_bedrock_on_the_namespace_s_role_is_unchanged() -> None:
    """The bucket role's trust still names the namespace's own account alone, and it holds no
    Bedrock action: the gateway's grant is its own role's, never added to the buckets'."""
    irsa = _artefacts(_engines(BEDROCK))["terraform/irsa.tf"]
    assert irsa == _artefacts(_engines())["terraform/irsa.tf"]
    assert re.findall(r"system:serviceaccount:\$\{var\.namespace\}:([a-z0-9.-]+)", irsa) == [
        NAMESPACE_ACCOUNT
    ]
    assert "bedrock" not in irsa.lower()


@pytest.mark.parametrize(
    ("gateway", "words"),
    [("ospreyflow", "differ"), ("Ospreyflow_Gateway", "Kubernetes name"),
     ("-gateway", "Kubernetes name")],
    ids=["same-as-the-namespace-s", "underscore-and-capitals", "leading-hyphen"],
)  # fmt: skip
def test_the_gateway_account_is_its_own_and_a_kubernetes_name(gateway: str, words: str) -> None:
    from harness.cloud_platform.settings import IrsaSettings
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match=words):
        IrsaSettings(service_account="ospreyflow", gateway_service_account=gateway)
    with pytest.raises(ValidationError, match="Kubernetes name"):
        IrsaSettings(service_account="Osprey Flow")


def test_bedrock_on_a_platform_naming_no_gateway_account_is_refused_in_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import harness.cloud_platform as cloud_platform

    real = cloud_platform.load_platform

    def without_the_gateway_account(name: str) -> Any:
        platform = real(name)
        irsa = platform.secrets.irsa.model_copy(update={"gateway_service_account": None})
        return platform.model_copy(
            update={"secrets": platform.secrets.model_copy(update={"irsa": irsa})}
        )

    monkeypatch.setattr(cloud_platform, "load_platform", without_the_gateway_account)
    with pytest.raises(cloud_platform.CloudPlatformNotRenderable, match="gateway_service_account"):
        _artefacts(_engines(BEDROCK))
    _artefacts(_engines(GEMINI))  # no Bedrock, no account needed


def test_no_other_terraform_file_names_the_gateway_s_role_policy_or_account() -> None:
    for declared in ([BEDROCK], [BEDROCK, GATEWAY, GEMINI]):
        assert stray_gateway_references(_artefacts(_engines(*declared))) == []


@pytest.mark.parametrize(
    "stray",
    [
        'resource "aws_iam_role_policy_attachment" "buckets_bedrock" {\n'
        "  role       = aws_iam_role.service.name\n"
        "  policy_arn = aws_iam_policy.gateway_bedrock.arn\n}\n",
        'resource "aws_iam_role_policy_attachment" "gateway_buckets" {\n'
        "  role       = aws_iam_role.gateway.name\n"
        "  policy_arn = aws_iam_policy.buckets.arn\n}\n",
        '    values = ["system:serviceaccount:${var.namespace}:ospreyflow-gateway"]\n',
    ],
    ids=["gateway-policy-on-the-bucket-role", "bucket-policy-on-the-gateway-role",
         "gateway-account-in-another-trust"],
)  # fmt: skip
def test_the_stray_check_flags_a_reference_planted_in_another_file(stray: str) -> None:
    artefacts = dict(_artefacts(_engines(BEDROCK)))
    assert stray_gateway_references(artefacts) == []
    artefacts["terraform/irsa.tf"] += "\n" + stray
    assert stray_gateway_references(artefacts)


@pytest.mark.parametrize(
    "engine",
    [BEDROCK, {**BEDROCK, "region": None}, GATEWAY, GEMINI,
     {"name": "openai", "roles": {"extraction": "gpt-4o-mini"}}],
    ids=["bedrock", "bedrock-no-region", "gateway", "gemini", "openai"],
)  # fmt: skip
def test_the_conduit_places_an_engine_s_host_as_the_render_does(engine: dict[str, Any]) -> None:
    """`RoutesMade.host_of` (the Conduit's) and `engine_host` (the render's) give the same host for
    every kind, the `{region}` placeholder and Bedrock's default region included (the
    orchestrator's round 2, minor)."""
    from harness.cloud_platform import engine_host, load_profile
    from services.api.model_admin import RoutesMade

    from schemas.deployment import ModelProviderConfig

    values = _values(_engines(BEDROCK, GATEWAY, GEMINI))
    made = RoutesMade.from_env({k: str(v) for k, v in values["environment"].items()})
    assert made is not None
    provider = ModelProviderConfig.model_validate(engine)
    rendered = engine_host(
        provider.name, provider.kind, provider.api_base, provider.region, load_profile()
    )
    assert made.host_of(provider) == rendered and rendered
