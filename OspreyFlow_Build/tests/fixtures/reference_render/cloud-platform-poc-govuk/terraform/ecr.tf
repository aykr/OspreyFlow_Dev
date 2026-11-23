# Decision 8: a repository for each image, scanned on push; `ospreyflow images push
# --registry` copies ours and the third-party ones into them, by digest.

locals {
  repositories = toset([
    "arcadedata/arcadedb",
    "clickhouse/clickhouse-server",
    "ospreyflow/api",
    "ospreyflow/laurium",
    "ospreyflow/litellm",
    "ospreyflow/ner",
    "ospreyflow/worker",
    "ospreyflow/workspace",
    "postgres",
  ])
}

resource "aws_ecr_repository" "image" {
  for_each             = local.repositories
  name                 = each.key
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
  }
}
