# Decisions 4 and 6: the buckets the services name as <prefix><name>, private, encrypted.
# A bucket's name is global across every AWS account, so the prefix carries a suffix
# made here.

resource "random_id" "buckets" {
  byte_length = 4
}

locals {
  buckets = toset(["media", "staging", "site-images", "tile-cache"])
  prefix  = "${var.namespace}-${random_id.buckets.hex}-"
}

resource "aws_s3_bucket" "store" {
  for_each = local.buckets
  bucket   = "${local.prefix}${each.key}"
}

resource "aws_s3_bucket_public_access_block" "store" {
  for_each                = local.buckets
  bucket                  = aws_s3_bucket.store[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "store" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.store[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.store["media"].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "kubernetes_secret" "s3_bucket_output" {
  metadata {
    name      = "s3-bucket-output"
    namespace = var.namespace
  }

  data = {
    bucket_prefix = local.prefix
  }
}
