"""The S3 stand-in refuses what S3, STS and KMS refuse (rule 15's second example), each refusal
reached through botocore as the backup runner reaches it: by IRSA's web identity, never a key.

A grant alone would prove the stand-in agrees with our hopes; each case here is a request the real
services refuse, with the code they refuse it by.
"""

from __future__ import annotations

import botocore.session
import pytest
from harness import cloud_platform_backups as backups
from botocore.exceptions import ClientError

from tests.cloud_platform_backup.conftest import (
    ACCOUNT,
    BUCKET,
    CONDUIT_ROLE_ARN,
    ISSUER_SECRET,
    KEY_ARN,
    PATH_STYLE,
    REGION,
    CLICKHOUSE_ROLE_ARN,
    ROLE_ARN,
    Running,
    later,
    role_policy,
    _deny_kms,
    standin_config,
)
from tests.fixtures.cloud_platform.s3_standin import Role, mint_token


def _code(error: pytest.ExceptionInfo[ClientError]) -> str:
    return str(error.value.response["Error"]["Code"])


def test_the_backup_role_writes_and_reads_its_bucket_encrypted_by_its_key(aws: Running) -> None:
    s3 = aws.s3()
    s3.put_object(Bucket=BUCKET, Key="sets/a/arcadedb/ospreyflow.zip", Body=b"zip")
    head = s3.head_object(Bucket=BUCKET, Key="sets/a/arcadedb/ospreyflow.zip")
    assert head["ServerSideEncryption"] == "aws:kms"
    assert head["SSEKMSKeyId"] == KEY_ARN
    assert s3.get_object(Bucket=BUCKET, Key="sets/a/arcadedb/ospreyflow.zip")["Body"].read() == b"zip"
    listed = s3.list_objects_v2(Bucket=BUCKET, Prefix="sets/")
    assert [o["Key"] for o in listed["Contents"]] == ["sets/a/arcadedb/ospreyflow.zip"]


def test_a_multipart_upload_round_trips(aws: Running) -> None:
    s3 = aws.s3()
    data = b"x" * (5 * 1024 * 1024) + b"y" * 10
    upload = s3.create_multipart_upload(Bucket=BUCKET, Key="sets/a/arcadedb/big.zip")
    parts = []
    for number, chunk in enumerate((data[: 5 * 1024 * 1024], data[5 * 1024 * 1024 :]), start=1):
        part = s3.upload_part(Bucket=BUCKET, Key="sets/a/arcadedb/big.zip", UploadId=upload["UploadId"],
                              PartNumber=number, Body=chunk)  # fmt: skip
        parts.append({"PartNumber": number, "ETag": part["ETag"]})
    s3.complete_multipart_upload(Bucket=BUCKET, Key="sets/a/arcadedb/big.zip", UploadId=upload["UploadId"],
                                 MultipartUpload={"Parts": parts})  # fmt: skip
    assert s3.get_object(Bucket=BUCKET, Key="sets/a/arcadedb/big.zip")["Body"].read() == data


def test_a_wrong_secret_is_refused_by_its_signature(aws: Running) -> None:
    aws.s3().list_objects_v2(Bucket=BUCKET)  # a session exists
    key, session = next(iter(aws.stand_in.sessions.items()))
    s3 = botocore.session.get_session().create_client("s3", endpoint_url=aws.endpoint, region_name=REGION,
                      aws_access_key_id=key, aws_secret_access_key="not-" + session.secret,
                      aws_session_token=session.token,
                      config=PATH_STYLE)  # fmt: skip
    with pytest.raises(ClientError) as refused:
        s3.list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "SignatureDoesNotMatch"


def test_an_unknown_key_is_refused(aws: Running) -> None:
    s3 = botocore.session.get_session().create_client("s3", endpoint_url=aws.endpoint, region_name=REGION,
                      aws_access_key_id="AKIANOTAKEY", aws_secret_access_key="x",
                      config=PATH_STYLE)  # fmt: skip
    with pytest.raises(ClientError) as refused:
        s3.list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "InvalidAccessKeyId"


def test_an_expired_role_is_refused(aws: Running) -> None:
    """The role's session expires (an hour on the platform): S3 says `ExpiredToken`. A client
    holding frozen credentials, as ClickHouse is handed them, cannot refresh them."""
    frozen = aws.session().get_credentials().get_frozen_credentials()
    s3 = botocore.session.get_session().create_client("s3", endpoint_url=aws.endpoint, region_name=REGION,
                      aws_access_key_id=frozen.access_key, aws_secret_access_key=frozen.secret_key,
                      aws_session_token=frozen.token,
                      config=PATH_STYLE)  # fmt: skip
    s3.list_objects_v2(Bucket=BUCKET)
    aws.stand_in.expire()
    with pytest.raises(ClientError) as refused:
        s3.list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "ExpiredToken"
    assert refused.value.response["Error"]["Message"] == "The provided token has expired."


def test_a_session_key_without_its_token_is_refused(aws: Running) -> None:
    frozen = aws.session().get_credentials().get_frozen_credentials()
    s3 = botocore.session.get_session().create_client("s3", endpoint_url=aws.endpoint, region_name=REGION,
                      aws_access_key_id=frozen.access_key, aws_secret_access_key=frozen.secret_key,
                      config=PATH_STYLE)  # fmt: skip
    with pytest.raises(ClientError) as refused:
        s3.list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "InvalidToken"


def test_a_skewed_clock_is_refused(aws: Running) -> None:
    s3 = aws.s3()
    s3.list_objects_v2(Bucket=BUCKET)
    later(aws.stand_in, 16 * 60)
    with pytest.raises(ClientError) as refused:
        s3.list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "RequestTimeTooSkewed"


def test_a_token_for_another_service_account_is_refused_by_sts(aws: Running) -> None:
    aws.token = (mint_token(ISSUER_SECRET, sub="system:serviceaccount:ospreyflow-dev:other"))
    with pytest.raises(ClientError) as refused:
        aws.s3().list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "AccessDenied"


def test_a_token_another_issuer_signed_is_refused_by_sts(aws: Running) -> None:
    aws.token = (mint_token("another-issuer", sub="system:serviceaccount:ospreyflow-dev:ospreyflow-backup"))
    with pytest.raises(ClientError) as refused:
        aws.s3().list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "InvalidIdentityToken"


def test_a_token_for_another_audience_is_refused_by_sts(aws: Running) -> None:
    aws.token = (mint_token(
        ISSUER_SECRET, sub="system:serviceaccount:ospreyflow-dev:ospreyflow-backup", aud="kubernetes"))  # fmt: skip
    with pytest.raises(ClientError) as refused:
        aws.s3().list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "AccessDenied"


def test_without_kms_generate_data_key_a_write_is_refused_naming_the_key(aws: Running) -> None:
    _deny_kms(aws, "kms:Decrypt")
    with pytest.raises(ClientError) as refused:
        aws.s3().put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x")
    assert _code(refused) == "AccessDenied"
    message = refused.value.response["Error"]["Message"]
    assert "kms:GenerateDataKey" in message and KEY_ARN in message


def test_without_kms_decrypt_a_read_and_a_multipart_completion_are_refused(aws: Running) -> None:
    aws.s3().put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x")
    _deny_kms(aws, "kms:GenerateDataKey")
    s3 = aws.s3()
    with pytest.raises(ClientError) as refused:
        s3.get_object(Bucket=BUCKET, Key="sets/a/arcadedb/x")
    assert _code(refused) == "AccessDenied"
    assert "kms:Decrypt" in refused.value.response["Error"]["Message"]
    upload = s3.create_multipart_upload(Bucket=BUCKET, Key="sets/a/arcadedb/big")
    part = s3.upload_part(Bucket=BUCKET, Key="sets/a/arcadedb/big", UploadId=upload["UploadId"], PartNumber=1, Body=b"y")
    with pytest.raises(ClientError) as refused:
        s3.complete_multipart_upload(Bucket=BUCKET, Key="sets/a/arcadedb/big", UploadId=upload["UploadId"],
                                     MultipartUpload={"Parts": [{"PartNumber": 1, "ETag": part["ETag"]}]})  # fmt: skip
    assert _code(refused) == "AccessDenied"


def test_plain_http_is_refused_by_the_bucket_policy(aws: Running) -> None:
    aws.stand_in.secure = False
    with pytest.raises(ClientError) as refused:
        aws.s3().list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "AccessDenied"


def test_another_encryption_or_another_key_is_refused_by_the_bucket_policy(aws: Running) -> None:
    s3 = aws.s3()
    with pytest.raises(ClientError) as refused:
        s3.put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x", ServerSideEncryption="AES256")
    assert _code(refused) == "AccessDenied"
    with pytest.raises(ClientError) as refused:
        s3.put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x", ServerSideEncryption="aws:kms",
                      SSEKMSKeyId=KEY_ARN.replace("1234abcd", "ffffffff"))  # fmt: skip
    assert _code(refused) == "AccessDenied"


def test_another_key_the_role_may_use_is_refused_by_the_bucket_policy_alone(aws: Running) -> None:
    """`ItsOwnKey` shown by itself (the lane-reviewer's finding): with the role given KMS on every key,
    a write under another key passes KMS and is refused by the bucket's policy, in its own words."""
    found = aws.stand_in.roles[ROLE_ARN]
    policy = role_policy()
    for statement in policy["Statement"]:
        if statement["Action"][0].startswith("kms:"):
            statement["Resource"] = ["*"]
    found.policies = [policy]
    with pytest.raises(ClientError) as refused:
        aws.s3().put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x", ServerSideEncryption="aws:kms",
                            SSEKMSKeyId=KEY_ARN.replace("1234abcd", "ffffffff"))  # fmt: skip
    assert _code(refused) == "AccessDenied"
    assert "kms:" not in refused.value.response["Error"]["Message"], "refused by the bucket, not by KMS"


def test_the_conduits_role_is_refused_the_backups_bucket(aws: Running) -> None:
    """Its own policy allows every S3 action; the bucket's denies it every object and version all the
    same. Listing is not denied (HeadBucket needs it: the Terraform's read, the decommission's step
    8), and names sets without holding any."""
    aws.s3().put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"zip")
    aws.token = (mint_token(ISSUER_SECRET, sub="system:serviceaccount:ospreyflow-dev:ospreyflow"))
    conduit = aws.s3(role=CONDUIT_ROLE_ARN)
    conduit.list_objects_v2(Bucket=BUCKET)
    for refused_call in (lambda: conduit.get_object(Bucket=BUCKET, Key="sets/a/arcadedb/x"),
                         lambda: conduit.delete_object(Bucket=BUCKET, Key="sets/a/arcadedb/x")):  # fmt: skip
        with pytest.raises(ClientError) as refused:
            refused_call()
        assert _code(refused) == "AccessDenied"
    assert aws.stand_in.read(BUCKET, "sets/a/arcadedb/x") == b"zip"
    with pytest.raises(ClientError) as refused:
        conduit.put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x")
    assert _code(refused) == "AccessDenied"


def test_an_action_the_role_is_not_given_is_refused(aws: Running) -> None:
    with pytest.raises(ClientError) as refused:
        aws.s3().put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
    assert _code(refused) == "AccessDenied"
    with pytest.raises(ClientError) as refused:
        aws.s3().list_objects_v2(Bucket="another-tenants-bucket")
    assert _code(refused) == "NoSuchBucket"


def test_a_missing_key_is_404_with_list_and_never_reveals_without(aws: Running) -> None:
    with pytest.raises(ClientError) as refused:
        aws.s3().get_object(Bucket=BUCKET, Key="sets/none/manifest.json")
    assert _code(refused) == "NoSuchKey"


def _with_policy(role: Role, policy: dict[str, object]) -> Role:
    return Role(arn=role.arn, policies=[policy], issuer_secret=role.issuer_secret,
                subject=role.subject, audience=role.audience, max_seconds=role.max_seconds)  # fmt: skip


def test_a_role_trusting_the_clusters_keys_takes_its_signed_token_and_refuses_another(aws: Running) -> None:
    """On kind the stand-in trusts the cluster's own issuer, as IRSA's OIDC provider does: RS256
    by its published keys, its `iss` the cluster's."""
    import json as _json

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = _json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    role = aws.stand_in.roles[ROLE_ARN]
    role.jwks, role.issuer = {"keys": [{**public, "kid": "k1"}]}, "https://kubernetes.default.svc"
    role.trust = backups.trust_policy(f"arn:aws:iam::{ACCOUNT}:oidc-provider/kubernetes.default.svc",
                                      "kubernetes.default.svc", role.subject)  # fmt: skip

    def token(signer: rsa.RSAPrivateKey, issuer: str = "https://kubernetes.default.svc") -> str:
        import time

        claims = {"sub": role.subject, "aud": ["sts.amazonaws.com"], "iss": issuer,
                  "exp": int(time.time()) + 600}  # fmt: skip
        return jwt.encode(claims, signer, algorithm="RS256", headers={"kid": "k1"})

    aws.token = (token(key))
    aws.s3().list_objects_v2(Bucket=BUCKET)
    for refused_token in (token(other), token(key, issuer="https://another.issuer")):
        aws.stand_in.sessions.clear()
        aws.token = (refused_token)
        with pytest.raises(ClientError) as refused:
            aws.s3().list_objects_v2(Bucket=BUCKET)
        assert _code(refused) == "InvalidIdentityToken"


def _lever(aws: Running, path: str, body: dict[str, object] | None = None) -> int:
    import json
    import urllib.request

    request = urllib.request.Request(aws.endpoint + path, data=json.dumps(body or {}).encode(), method="POST")
    with urllib.request.urlopen(request) as answer:  # noqa: S310 - the stand-in's own address
        return int(answer.status)


def test_a_policy_changed_by_the_lever_judges_the_sessions_already_running(aws: Running) -> None:
    """As on AWS: a role's policy changed while a session lives is the policy that session meets
    next, and the session goes on (ClickHouse keeps its session; ending it at a policy change
    would refuse it for the wrong reason, an unknown key)."""
    client = aws.s3()
    client.put_object(Bucket=BUCKET, Key="sets/a/arcadedb/before", Body=b"x")
    sessions = dict(aws.stand_in.sessions)
    assert _lever(aws, "/_standin/configure", standin_config(key_policy=_key_policy_without(ROLE_ARN))) == 204
    with pytest.raises(ClientError) as refused:
        client.put_object(Bucket=BUCKET, Key="sets/a/arcadedb/after", Body=b"x")
    assert _code(refused) == "AccessDenied"
    assert "kms:GenerateDataKey" in refused.value.response["Error"]["Message"]
    assert _lever(aws, "/_standin/configure", standin_config()) == 204
    client.put_object(Bucket=BUCKET, Key="sets/a/arcadedb/after", Body=b"x")
    assert aws.stand_in.sessions.keys() == sessions.keys()
    assert aws.stand_in.read(BUCKET, "sets/a/arcadedb/before") == b"x", "the objects are kept"


def test_the_expire_lever_ends_every_session_as_an_hour_would(aws: Running) -> None:
    client = aws.s3()
    client.list_objects_v2(Bucket=BUCKET)
    assert _lever(aws, "/_standin/expire") == 204
    with pytest.raises(ClientError) as refused:
        client.put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x")
    assert _code(refused) == "ExpiredToken"


@pytest.mark.parametrize(("role", "key"), [
    (ROLE_ARN, "sets/a/arcadedb/x"), (ROLE_ARN, "sets/a/manifest.json"), (ROLE_ARN, "sets/a/claims/ingest.tar.gz"),
    (CLICKHOUSE_ROLE_ARN, "sets/a/clickhouse/data.bin"), (CLICKHOUSE_ROLE_ARN, "sets/a/clickhouse/.lock.old"),
])  # fmt: skip
def test_each_backup_role_is_refused_every_delete_but_clickhouses_lock(aws: Running, role: str, key: str) -> None:
    """Each role's policy as backups.tf writes it: a set's data, its manifest, anything but
    ClickHouse's own lock file, is never erased by either."""
    client = aws.s3(role)
    client.put_object(Bucket=BUCKET, Key=key, Body=b"x")
    with pytest.raises(ClientError) as refused:
        client.delete_object(Bucket=BUCKET, Key=key)
    assert _code(refused) == "AccessDenied"
    assert aws.stand_in.read(BUCKET, key) == b"x"


@pytest.mark.parametrize(("role", "key"), [
    (ROLE_ARN, "sets/a/clickhouse/data.bin"), (CLICKHOUSE_ROLE_ARN, "sets/a/arcadedb/ospreyflow.zip"),
    (CLICKHOUSE_ROLE_ARN, "sets/a/manifest.json"), (CLICKHOUSE_ROLE_ARN, "sets/a/claims/ingest.tar.gz"),
])  # fmt: skip
def test_each_role_is_refused_the_other_roles_prefix(aws: Running, role: str, key: str) -> None:
    """The orchestrator's ruling 1(b): ClickHouse's role reaches `sets/*/clickhouse/*` alone, so a
    query reaching ClickHouse can neither read the graph's zip nor write a manifest; the runner's
    never touches ClickHouse's part."""
    with pytest.raises(ClientError) as refused:
        aws.s3(role).put_object(Bucket=BUCKET, Key=key, Body=b"x")
    assert _code(refused) == "AccessDenied"
    with pytest.raises(ClientError) as refused:
        aws.s3(role).get_object(Bucket=BUCKET, Key=key)
    assert _code(refused) in {"AccessDenied", "NoSuchKey"}
    if _code(refused) == "NoSuchKey":
        pytest.fail("a read of the other role's prefix answered as though it might hold it")


def test_clickhouses_role_may_remove_its_lock_and_nothing_else(aws: Running) -> None:
    client = aws.s3(CLICKHOUSE_ROLE_ARN)
    client.put_object(Bucket=BUCKET, Key="sets/a/clickhouse/.lock", Body=b"")
    client.delete_object(Bucket=BUCKET, Key="sets/a/clickhouse/.lock")
    assert aws.stand_in.meta(BUCKET, "sets/a/clickhouse/.lock") is None


def test_aws_kms_named_without_a_key_is_refused_by_the_bucket_policy(aws: Running) -> None:
    """`aws:kms` with no key named is S3's own AWS-managed key, not the bucket's, and needs no grant
    on the bucket's key: only the bucket's policy (`NoKeyNamed`) refuses it."""
    with pytest.raises(ClientError) as refused:
        aws.s3().put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x", ServerSideEncryption="aws:kms")
    assert _code(refused) == "AccessDenied"


def test_a_request_signed_for_another_region_is_refused(aws: Running) -> None:
    client = aws.session().create_client("s3", region_name="us-east-1", endpoint_url=aws.endpoint, config=PATH_STYLE)
    with pytest.raises(ClientError) as refused:
        client.list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "AuthorizationHeaderMalformed"
    assert "expecting 'eu-west-2'" in refused.value.response["Error"]["Message"]


def _key_policy_without(role: str) -> dict[str, object]:
    return backups.key_policy(f"arn:aws:iam::{ACCOUNT}:root",
                              [r for r in (ROLE_ARN, CLICKHOUSE_ROLE_ARN) if r != role], REGION)  # fmt: skip


def test_a_role_the_keys_own_policy_leaves_out_is_refused_whatever_its_iam_says(aws: Running) -> None:
    """KMS as AWS runs it (the lane-reviewer's round 2): the key's own policy names the roles; one it
    leaves out is refused though its IAM policy grants the key."""
    aws.stand_in.keys[KEY_ARN] = _key_policy_without(ROLE_ARN)
    with pytest.raises(ClientError) as refused:
        aws.s3().put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x")
    assert _code(refused) == "AccessDenied"
    assert "no resource-based policy allows the kms:GenerateDataKey action" in refused.value.response["Error"]["Message"]


def test_the_keys_own_grant_is_enough_without_the_roles_iam(aws: Running) -> None:
    """And the other way: a role the key's policy names uses the key with no KMS in its IAM policy."""
    found = aws.stand_in.roles[ROLE_ARN]
    found.policies = [role_policy(kms_actions=())]
    aws.s3().put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x")
    assert aws.stand_in.meta(BUCKET, "sets/a/arcadedb/x")["kms_key"] == KEY_ARN


def test_the_key_used_other_than_through_s3_is_refused(aws: Running) -> None:
    """`kms:ViaService` in the key's own policy: the stand-in's KMS is asked by S3, so it is S3 in the
    region; a key policy naming another service refuses."""
    policy = backups.key_policy(f"arn:aws:iam::{ACCOUNT}:root", [ROLE_ARN, CLICKHOUSE_ROLE_ARN], "us-east-1")
    aws.stand_in.keys[KEY_ARN] = policy
    aws.stand_in.roles[ROLE_ARN].policies = [role_policy(kms_actions=())]
    with pytest.raises(ClientError) as refused:
        aws.s3().put_object(Bucket=BUCKET, Key="sets/a/arcadedb/x", Body=b"x")
    assert _code(refused) == "AccessDenied"


def test_a_token_of_another_issuer_is_refused_by_the_trust_though_signed_by_a_trusted_key(aws: Running) -> None:
    """The trust's federated principal is one cluster's issuer: a token naming another issuer meets no
    statement, whoever signed it (the orchestrator's round 2, item 14)."""
    aws.token = mint_token(ISSUER_SECRET, sub="system:serviceaccount:ospreyflow-dev:ospreyflow-backup",
                           iss="https://oidc.eks.eu-west-2.amazonaws.com/id/ANOTHER")  # fmt: skip
    with pytest.raises(ClientError) as refused:
        aws.s3().list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "AccessDenied"


def test_a_completion_naming_a_part_not_uploaded_or_by_another_etag_is_refused_as_s3_does(aws: Running) -> None:
    """S3 answers a completion naming a part it does not hold, or by an ETag that is not the part's,
    with 400 InvalidPart, and keeps the upload (it may be completed again, or aborted)."""
    s3 = aws.s3()
    key = "sets/a/arcadedb/big.zip"
    upload = s3.create_multipart_upload(Bucket=BUCKET, Key=key)
    first = s3.upload_part(Bucket=BUCKET, Key=key, UploadId=upload["UploadId"], PartNumber=1,
                           Body=b"x" * (5 * 1024 * 1024))  # fmt: skip
    last = s3.upload_part(Bucket=BUCKET, Key=key, UploadId=upload["UploadId"], PartNumber=2, Body=b"y")
    for parts in ([{"PartNumber": 1, "ETag": first["ETag"]}, {"PartNumber": 3, "ETag": last["ETag"]}],
                  [{"PartNumber": 1, "ETag": first["ETag"]}, {"PartNumber": 2, "ETag": '"0" * 32'}]):  # fmt: skip
        with pytest.raises(ClientError) as refused:
            s3.complete_multipart_upload(Bucket=BUCKET, Key=key, UploadId=upload["UploadId"],
                                         MultipartUpload={"Parts": parts})  # fmt: skip
        assert _code(refused) == "InvalidPart"
        assert refused.value.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    with pytest.raises(ClientError) as refused:
        s3.complete_multipart_upload(Bucket=BUCKET, Key=key, UploadId=upload["UploadId"], MultipartUpload={
            "Parts": [{"PartNumber": 2, "ETag": last["ETag"]}, {"PartNumber": 1, "ETag": first["ETag"]}]})  # fmt: skip
    assert _code(refused) == "InvalidPartOrder"
    s3.complete_multipart_upload(Bucket=BUCKET, Key=key, UploadId=upload["UploadId"], MultipartUpload={
        "Parts": [{"PartNumber": 1, "ETag": first["ETag"]}, {"PartNumber": 2, "ETag": last["ETag"]}]})  # fmt: skip
    assert s3.head_object(Bucket=BUCKET, Key=key)["ContentLength"] == 5 * 1024 * 1024 + 1


def test_a_part_under_five_mib_but_the_last_is_refused_as_s3_does(aws: Running) -> None:
    s3 = aws.s3()
    key = "sets/a/arcadedb/small.zip"
    upload = s3.create_multipart_upload(Bucket=BUCKET, Key=key)
    parts = []
    for number, body in ((1, b"x" * 1024), (2, b"y")):
        part = s3.upload_part(Bucket=BUCKET, Key=key, UploadId=upload["UploadId"], PartNumber=number, Body=body)
        parts.append({"PartNumber": number, "ETag": part["ETag"]})
    with pytest.raises(ClientError) as refused:
        s3.complete_multipart_upload(Bucket=BUCKET, Key=key, UploadId=upload["UploadId"],
                                     MultipartUpload={"Parts": parts})  # fmt: skip
    assert _code(refused) == "EntityTooSmall"
    assert refused.value.response["ResponseMetadata"]["HTTPStatusCode"] == 400


def test_a_key_pending_deletion_is_refused_for_every_use(aws: Running) -> None:
    """Decommission step 7's destroy schedules the key's deletion: from then on KMS refuses every
    use of it, whoever asks (`KMSInvalidStateException`, passed on by S3), until the deletion is
    cancelled. R1's destroy stand-in sets the key so (`r1_kind.decommission_resources`)."""
    s3 = aws.s3()
    s3.put_object(Bucket=BUCKET, Key="sets/a/arcadedb/ospreyflow.zip", Body=b"zip")
    config = standin_config()
    config["keys"][0]["state"] = "PendingDeletion"
    aws.stand_in.configure(config)
    for act in (
        lambda: s3.put_object(Bucket=BUCKET, Key="sets/b/arcadedb/x", Body=b"x"),
        lambda: s3.get_object(Bucket=BUCKET, Key="sets/a/arcadedb/ospreyflow.zip"),
    ):
        with pytest.raises(ClientError) as refused:
            act()
        assert _code(refused) == "KMS.KMSInvalidStateException"
        assert f"{KEY_ARN} is pending deletion" in refused.value.response["Error"]["Message"]
    del config["keys"][0]["state"]  # cancel-key-deletion
    aws.stand_in.configure(config)
    read = s3.get_object(Bucket=BUCKET, Key="sets/a/arcadedb/ospreyflow.zip")
    assert read["Body"].read() == b"zip"
