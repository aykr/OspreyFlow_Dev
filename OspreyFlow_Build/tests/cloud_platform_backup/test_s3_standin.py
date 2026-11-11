"""The S3 stand-in refuses what S3, STS and KMS refuse (rule 15's second example), each refusal
reached through botocore as the backup runner reaches it: by IRSA's web identity, never a key.

A grant alone would prove the stand-in agrees with our hopes; each case here is a request the real
services refuse, with the code they refuse it by.
"""

from __future__ import annotations

import botocore.session
import pytest
from botocore.exceptions import ClientError

from tests.cloud_platform_backup.conftest import (
    BUCKET,
    CONDUIT_ROLE_ARN,
    ISSUER_SECRET,
    PATH_STYLE,
    KEY_ARN,
    REGION,
    ROLE_ARN,
    Running,
    later,
    role_policy,
)
from tests.fixtures.cloud_platform.s3_standin import Role, mint_token


def _code(error: pytest.ExceptionInfo[ClientError]) -> str:
    return str(error.value.response["Error"]["Code"])


def test_the_backup_role_writes_and_reads_its_bucket_encrypted_by_its_key(aws: Running) -> None:
    s3 = aws.s3()
    s3.put_object(Bucket=BUCKET, Key="sets/a/arcadedb.zip", Body=b"zip")
    head = s3.head_object(Bucket=BUCKET, Key="sets/a/arcadedb.zip")
    assert head["ServerSideEncryption"] == "aws:kms"
    assert head["SSEKMSKeyId"] == KEY_ARN
    assert s3.get_object(Bucket=BUCKET, Key="sets/a/arcadedb.zip")["Body"].read() == b"zip"
    listed = s3.list_objects_v2(Bucket=BUCKET, Prefix="sets/")
    assert [o["Key"] for o in listed["Contents"]] == ["sets/a/arcadedb.zip"]


def test_a_multipart_upload_round_trips(aws: Running) -> None:
    s3 = aws.s3()
    data = b"x" * (5 * 1024 * 1024) + b"y" * 10
    upload = s3.create_multipart_upload(Bucket=BUCKET, Key="sets/a/big.zip")
    parts = []
    for number, chunk in enumerate((data[: 5 * 1024 * 1024], data[5 * 1024 * 1024 :]), start=1):
        part = s3.upload_part(Bucket=BUCKET, Key="sets/a/big.zip", UploadId=upload["UploadId"],
                              PartNumber=number, Body=chunk)  # fmt: skip
        parts.append({"PartNumber": number, "ETag": part["ETag"]})
    s3.complete_multipart_upload(Bucket=BUCKET, Key="sets/a/big.zip", UploadId=upload["UploadId"],
                                 MultipartUpload={"Parts": parts})  # fmt: skip
    assert s3.get_object(Bucket=BUCKET, Key="sets/a/big.zip")["Body"].read() == data


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
    aws.token_file.write_text(mint_token(ISSUER_SECRET, sub="system:serviceaccount:ospreyflow-dev:other"))
    with pytest.raises(ClientError) as refused:
        aws.s3().list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "AccessDenied"


def test_a_token_another_issuer_signed_is_refused_by_sts(aws: Running) -> None:
    aws.token_file.write_text(mint_token("another-issuer", sub="system:serviceaccount:ospreyflow-dev:ospreyflow-backup"))
    with pytest.raises(ClientError) as refused:
        aws.s3().list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "InvalidIdentityToken"


def test_a_token_for_another_audience_is_refused_by_sts(aws: Running) -> None:
    aws.token_file.write_text(mint_token(
        ISSUER_SECRET, sub="system:serviceaccount:ospreyflow-dev:ospreyflow-backup", aud="kubernetes"))  # fmt: skip
    with pytest.raises(ClientError) as refused:
        aws.s3().list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "AccessDenied"


def test_without_kms_generate_data_key_a_write_is_refused_naming_the_key(aws: Running) -> None:
    aws.stand_in.roles[ROLE_ARN] = _with_policy(aws.stand_in.roles[ROLE_ARN], role_policy(kms_actions=("kms:Decrypt",)))
    with pytest.raises(ClientError) as refused:
        aws.s3().put_object(Bucket=BUCKET, Key="sets/a/x", Body=b"x")
    assert _code(refused) == "AccessDenied"
    message = refused.value.response["Error"]["Message"]
    assert "kms:GenerateDataKey" in message and KEY_ARN in message


def test_without_kms_decrypt_a_read_and_a_multipart_completion_are_refused(aws: Running) -> None:
    aws.s3().put_object(Bucket=BUCKET, Key="sets/a/x", Body=b"x")
    aws.stand_in.roles[ROLE_ARN] = _with_policy(
        aws.stand_in.roles[ROLE_ARN], role_policy(kms_actions=("kms:GenerateDataKey",)))  # fmt: skip
    aws.stand_in.sessions.clear()
    s3 = aws.s3()
    with pytest.raises(ClientError) as refused:
        s3.get_object(Bucket=BUCKET, Key="sets/a/x")
    assert _code(refused) == "AccessDenied"
    assert "kms:Decrypt" in refused.value.response["Error"]["Message"]
    upload = s3.create_multipart_upload(Bucket=BUCKET, Key="sets/a/big")
    part = s3.upload_part(Bucket=BUCKET, Key="sets/a/big", UploadId=upload["UploadId"], PartNumber=1, Body=b"y")
    with pytest.raises(ClientError) as refused:
        s3.complete_multipart_upload(Bucket=BUCKET, Key="sets/a/big", UploadId=upload["UploadId"],
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
        s3.put_object(Bucket=BUCKET, Key="sets/a/x", Body=b"x", ServerSideEncryption="AES256")
    assert _code(refused) == "AccessDenied"
    with pytest.raises(ClientError) as refused:
        s3.put_object(Bucket=BUCKET, Key="sets/a/x", Body=b"x", ServerSideEncryption="aws:kms",
                      SSEKMSKeyId=KEY_ARN.replace("1234abcd", "ffffffff"))  # fmt: skip
    assert _code(refused) == "AccessDenied"


def test_the_conduits_role_is_refused_the_backups_bucket(aws: Running) -> None:
    """Its own policy allows every S3 action; the bucket's denies it all the same."""
    aws.token_file.write_text(mint_token(ISSUER_SECRET, sub="system:serviceaccount:ospreyflow-dev:ospreyflow"))
    conduit = aws.s3(role=CONDUIT_ROLE_ARN)
    with pytest.raises(ClientError) as refused:
        conduit.list_objects_v2(Bucket=BUCKET)
    assert _code(refused) == "AccessDenied"
    with pytest.raises(ClientError) as refused:
        conduit.put_object(Bucket=BUCKET, Key="sets/a/x", Body=b"x")
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
        aws.s3().get_object(Bucket=BUCKET, Key="sets/none")
    assert _code(refused) == "NoSuchKey"


def _with_policy(role: Role, policy: dict[str, object]) -> Role:
    return Role(arn=role.arn, policies=[policy], issuer_secret=role.issuer_secret,
                subject=role.subject, audience=role.audience, max_seconds=role.max_seconds)  # fmt: skip
