# Decision 4: the service account the Conduit, the workers and the report sync run as,
# given the buckets through its role (IRSA), so no S3 key exists anywhere.

data "aws_iam_policy_document" "buckets" {
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [for bucket in aws_s3_bucket.store : bucket.arn]
  }

  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [for bucket in aws_s3_bucket.store : "${bucket.arn}/*"]
  }
}

resource "aws_iam_policy" "buckets" {
  name   = "${var.namespace}-buckets"
  policy = data.aws_iam_policy_document.buckets.json
}

data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.eks_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_issuer}:sub"
      values   = ["system:serviceaccount:${var.namespace}:ospreyflow"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_issuer}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "service" {
  name               = "${var.namespace}-service"
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

resource "aws_iam_role_policy_attachment" "buckets" {
  role       = aws_iam_role.service.name
  policy_arn = aws_iam_policy.buckets.arn
}

resource "kubernetes_service_account" "service" {
  metadata {
    name      = "ospreyflow"
    namespace = var.namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.service.arn
    }
  }
}
