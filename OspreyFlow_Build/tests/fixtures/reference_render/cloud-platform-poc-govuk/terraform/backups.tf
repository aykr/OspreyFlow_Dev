# Decision 13 (ADR-148 Amendment 7): the backups' bucket, versioned and encrypted by a key
# of its own; two roles, each trusted for its own service account and given its own prefix
# and this key through S3, nothing else; neither can erase a set.

data "aws_caller_identity" "backups" {

}

data "aws_iam_policy_document" "backups_key" {
  statement {
    sid       = "Administer"
    effect    = "Allow"
    actions   = ["kms:CreateAlias", "kms:DeleteAlias", "kms:UpdateAlias", "kms:Describe*", "kms:Enable*", "kms:List*", "kms:PutKeyPolicy", "kms:Update*", "kms:Revoke*", "kms:Disable*", "kms:Get*", "kms:TagResource", "kms:UntagResource", "kms:CancelKeyDeletion"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.backups.account_id}:root"]
    }
  }

  statement {
    sid       = "UseThroughS3"
    effect    = "Allow"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt", "kms:DescribeKey"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["${aws_iam_role.backup.arn}", "${aws_iam_role.backup_clickhouse.arn}"]
    }

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.eu-west-2.amazonaws.com"]
    }
  }

  statement {
    sid       = "NeverScheduledForDeletion"
    effect    = "Deny"
    actions   = ["kms:ScheduleKeyDeletion"]
    resources = ["*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_kms_key" "backups" {
  description             = "${var.namespace} backups"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.backups_key.json

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "backups" {
  name          = "alias/${var.namespace}-backups"
  target_key_id = aws_kms_key.backups.key_id
}

resource "aws_s3_bucket" "backups" {
  bucket = "${local.prefix}backups"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.backups.arn
    }

    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket     = aws_s3_bucket.backups.id
  depends_on = [aws_s3_bucket_versioning.backups]

  rule {
    id     = "abort-unfinished-uploads"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "expire-sets"
    status = "Enabled"

    filter {
      prefix = "sets/"
    }

    expiration {
      days = 34
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  rule {
    id     = "remove-expired-markers"
    status = "Enabled"

    filter {
      prefix = "sets/"
    }

    expiration {
      expired_object_delete_marker = true
    }
  }
}

data "aws_iam_policy_document" "backups_bucket" {
  statement {
    sid       = "TLSOnly"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = ["${aws_s3_bucket.backups.arn}", "${aws_s3_bucket.backups.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid       = "KMSOnly"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.backups.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }

    condition {
      test     = "Null"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["false"]
    }
  }

  statement {
    sid       = "ItsOwnKey"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.backups.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = ["${aws_kms_key.backups.arn}"]
    }

    condition {
      test     = "Null"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = ["false"]
    }
  }

  statement {
    sid       = "NoKeyNamed"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.backups.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }

    condition {
      test     = "Null"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = ["true"]
    }
  }

  statement {
    sid       = "BackupRolesOnly"
    effect    = "Deny"
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:PutObjectAcl", "s3:PutObjectVersionAcl", "s3:DeleteObject", "s3:DeleteObjectVersion", "s3:RestoreObject"]
    resources = ["${aws_s3_bucket.backups.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "ArnNotEquals"
      variable = "aws:PrincipalArn"
      values   = ["${aws_iam_role.backup.arn}", "${aws_iam_role.backup_clickhouse.arn}"]
    }
  }
}

resource "aws_s3_bucket_policy" "backups" {
  bucket = aws_s3_bucket.backups.id
  policy = data.aws_iam_policy_document.backups_bucket.json
}

data "aws_iam_policy_document" "backup_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["${var.eks_oidc_provider_arn}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_issuer}:sub"
      values   = ["system:serviceaccount:${var.namespace}:ospreyflow-backup"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_issuer}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backup" {
  name               = "${var.namespace}-backup"
  assume_role_policy = data.aws_iam_policy_document.backup_trust.json
}

data "aws_iam_policy_document" "backup_policy" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = ["${aws_s3_bucket.backups.arn}"]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.backups.arn}/sets/*/arcadedb/*", "${aws_s3_bucket.backups.arn}/sets/*/claims/*", "${aws_s3_bucket.backups.arn}/sets/*/manifest.json"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = ["${aws_kms_key.backups.arn}"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.eu-west-2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "backup" {
  name   = "${var.namespace}-backup"
  role   = aws_iam_role.backup.id
  policy = data.aws_iam_policy_document.backup_policy.json
}

resource "kubernetes_service_account" "backup" {
  metadata {
    name      = "ospreyflow-backup"
    namespace = var.namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.backup.arn
    }
  }
}

data "aws_iam_policy_document" "backup_clickhouse_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["${var.eks_oidc_provider_arn}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_issuer}:sub"
      values   = ["system:serviceaccount:${var.namespace}:ospreyflow-backup-clickhouse"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_issuer}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backup_clickhouse" {
  name               = "${var.namespace}-backup-clickhouse"
  assume_role_policy = data.aws_iam_policy_document.backup_clickhouse_trust.json
}

data "aws_iam_policy_document" "backup_clickhouse_policy" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = ["${aws_s3_bucket.backups.arn}"]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.backups.arn}/sets/*/clickhouse/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = ["${aws_kms_key.backups.arn}"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.eu-west-2.amazonaws.com"]
    }
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:DeleteObject"]
    resources = ["${aws_s3_bucket.backups.arn}/sets/*/clickhouse/.lock"]
  }
}

resource "aws_iam_role_policy" "backup_clickhouse" {
  name   = "${var.namespace}-backup-clickhouse"
  role   = aws_iam_role.backup_clickhouse.id
  policy = data.aws_iam_policy_document.backup_clickhouse_policy.json
}

resource "kubernetes_service_account" "backup_clickhouse" {
  metadata {
    name      = "ospreyflow-backup-clickhouse"
    namespace = var.namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.backup_clickhouse.arn
    }
  }
}

resource "random_password" "clickhouse_backup" {
  length  = 32
  special = false
}

resource "kubernetes_secret" "ospreyflow_clickhouse_backup" {
  metadata {
    name      = "ospreyflow-clickhouse-backup"
    namespace = var.namespace
  }

  data = {
    password = random_password.clickhouse_backup.result
  }
}

resource "kubernetes_secret" "ospreyflow_backup_output" {
  metadata {
    name      = "ospreyflow-backup-output"
    namespace = var.namespace
  }

  data = {
    bucket      = aws_s3_bucket.backups.bucket
    kms_key_arn = aws_kms_key.backups.arn
  }
}
