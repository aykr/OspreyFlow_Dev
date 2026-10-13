# Small on AWS (ADR-114 decision 8): one EC2 server running the deployment's containers, with the
# cloud's managed services underneath — RDS for PostgreSQL, S3, Secrets Manager, AWS Backup and EC2
# automatic recovery. Docker on the server restarts the stack; the cloud protects the data.
#
# Choices made here, not in the decision, and recorded in `process/07_BUILD_PLAN.md`'s B6 row:
# - nothing reaches the server from the internet but 80 (the HTTPS certificate challenge) and 443;
#   there is no SSH — an operator reaches the server through Systems Manager Session Manager;
# - the database password is made and kept by Secrets Manager (`manage_master_user_password`), so it
#   is never in this state file;
# - two availability zones, because RDS needs a subnet group across two, but one server.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { "ospreyflow:deployment" = var.name }
  }
}

locals {
  # Memory-optimised: a nominal 16 GiB server shows its system less than the 16 GiB floor
  # Preflight holds a deployment to, so the smallest is 32 GiB.
  server_type = { small = "r6i.xlarge", medium = "r6i.2xlarge", large = "r6i.4xlarge" }[var.size]
  db_class    = { small = "db.t4g.medium", medium = "db.m6g.large", large = "db.m6g.xlarge" }[var.size]
  zones       = slice(data.aws_availability_zones.here.names, 0, 2)
}

data "aws_availability_zones" "here" {
  state = "available"
}

data "aws_region" "here" {}

# Ubuntu 24.04 LTS from Canonical's own account.
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

# --- network ---------------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  availability_zone = local.zones[count.index]
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  tags              = { Name = "${var.name}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  availability_zone = local.zones[count.index]
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, 10 + count.index)
  tags              = { Name = "${var.name}-private-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "server" {
  name        = "${var.name}-server"
  description = "The OspreyFlow server: HTTP and HTTPS in, anything out"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.server.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
}

resource "aws_vpc_security_group_egress_rule" "server_out" {
  security_group_id = aws_security_group.server.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_security_group" "database" {
  name        = "${var.name}-database"
  description = "PostgreSQL, from the OspreyFlow server only"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "database_from_server" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.server.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

# --- data: database, object store, secrets ---------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "postgres" {
  identifier                  = var.name
  engine                      = "postgres"
  engine_version              = "16"
  instance_class              = local.db_class
  allocated_storage           = 50
  max_allocated_storage       = 500
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = "ospreyflow"
  username                    = "osprey"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.main.name
  vpc_security_group_ids      = [aws_security_group.database.id]
  publicly_accessible         = false
  backup_retention_period     = var.backup_days
  deletion_protection         = true
  skip_final_snapshot         = false
  final_snapshot_identifier   = "${var.name}-final"
  copy_tags_to_snapshot       = true
  auto_minor_version_upgrade  = true
}

# The S3 stores (05_DEPLOYMENT.md §3a): media, staged Parquet, site images and the tile cache,
# each `<prefix><name>` — bucket names are global, so the prefix carries a random part.
resource "random_id" "buckets" {
  byte_length = 3
}

locals {
  bucket_prefix = "${var.name}-${random_id.buckets.hex}-"
  stores        = toset(["media", "staging", "site-images", "tile-cache"])
}

resource "aws_s3_bucket" "store" {
  for_each = local.stores
  bucket   = "${local.bucket_prefix}${each.key}"
}

resource "aws_s3_bucket_public_access_block" "store" {
  for_each                = local.stores
  bucket                  = aws_s3_bucket.store[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "store" {
  for_each = local.stores
  bucket   = aws_s3_bucket.store[each.key].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.store["media"].id
  versioning_configuration {
    status = "Enabled"
  }
}

# The first administrator's one-time code (Amendment 10 point 4): written by the server's first
# boot, read once and deleted by the operator's install command. Made empty here.
resource "aws_secretsmanager_secret" "first_admin" {
  name_prefix             = "${var.name}-first-admin-"
  recovery_window_in_days = 0
}

# The deployment's own secrets (the sign-in client's, the service passwords), written by the
# install on the server; this only makes the place they are kept.
resource "aws_secretsmanager_secret" "deployment" {
  name_prefix = "${var.name}-deployment-"
}

# --- the server ----------------------------------------------------------------------------------

data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "server" {
  name_prefix        = "${var.name}-server-"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
}

resource "aws_iam_role_policy_attachment" "session_manager" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "server" {
  statement {
    sid     = "Stores"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = flatten([
      for bucket in aws_s3_bucket.store : [bucket.arn, "${bucket.arn}/*"]
    ])
  }
  statement {
    sid       = "FirstAdministratorCode"
    actions   = ["secretsmanager:PutSecretValue"]
    resources = [aws_secretsmanager_secret.first_admin.arn]
  }
  statement {
    sid       = "DeploymentSecrets"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"]
    resources = [aws_secretsmanager_secret.deployment.arn]
  }
  statement {
    sid       = "DatabasePassword"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_db_instance.postgres.master_user_secret[0].secret_arn]
  }
}

resource "aws_iam_role_policy" "server" {
  role   = aws_iam_role.server.id
  policy = data.aws_iam_policy_document.server.json
}

resource "aws_iam_instance_profile" "server" {
  name_prefix = "${var.name}-server-"
  role        = aws_iam_role.server.name
}

resource "aws_instance" "server" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = local.server_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.server.id]
  iam_instance_profile   = aws_iam_instance_profile.server.name
  user_data = templatefile("${path.module}/../cloud-init.yaml.tftpl", {
    provider           = "aws"
    repository         = var.repository
    release            = var.release
    domain             = var.domain
    region             = var.region
    answers            = yamlencode(local.answers)
    database_secret    = aws_db_instance.postgres.master_user_secret[0].secret_arn
    first_admin_secret = aws_secretsmanager_secret.first_admin.arn
    key_vault          = ""
  })
  metadata_options {
    http_tokens = "required"
  }
  root_block_device {
    volume_type = "gp3"
    volume_size = 200
    encrypted   = true
  }
  tags = { Name = var.name }
}

resource "aws_eip" "server" {
  instance = aws_instance.server.id
  domain   = "vpc"
}

# EC2 automatic recovery: a failed host check moves the instance to healthy hardware, keeping its
# address, disk and identity.
resource "aws_cloudwatch_metric_alarm" "recover" {
  alarm_name          = "${var.name}-recover"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  dimensions          = { InstanceId = aws_instance.server.id }
  alarm_actions       = ["arn:aws:automate:${data.aws_region.here.name}:ec2:recover"]
}

# --- backups -------------------------------------------------------------------------------------

resource "aws_backup_vault" "main" {
  name = var.name
}

resource "aws_backup_plan" "daily" {
  name = "${var.name}-daily"
  rule {
    rule_name         = "daily"
    target_vault_name = aws_backup_vault.main.name
    schedule          = "cron(0 3 * * ? *)"
    lifecycle {
      delete_after = var.backup_days
    }
  }
}

data "aws_iam_policy_document" "assume_backup" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backup" {
  name_prefix        = "${var.name}-backup-"
  assume_role_policy = data.aws_iam_policy_document.assume_backup.json
}

resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_backup_selection" "server" {
  name         = "${var.name}-server"
  plan_id      = aws_backup_plan.daily.id
  iam_role_arn = aws_iam_role.backup.arn
  resources    = [aws_instance.server.arn]
}

# --- the install's answers, and the names (Amendment 10 points 1 and 3) ---------------------------

locals {
  # What the server's first boot installs from: no secret in it — the passwords are read on the
  # server with its own identity.
  answers = {
    mode = "small"
    cloud = merge(
      { provider = "aws", region = var.region, domain = var.domain },
      var.admin_email == "" ? {} : { admin_email = var.admin_email },
    )
    external = {
      postgres = {
        host     = aws_db_instance.postgres.address
        port     = 5432
        database = "ospreyflow"
        user     = "osprey"
        sslmode  = "require"
      }
      object_store = {
        endpoint      = "s3.${var.region}.amazonaws.com"
        region        = var.region
        credentials   = "instance"
        bucket_prefix = local.bucket_prefix
      }
    }
  }
  names = [var.domain, "id.${var.domain}", "bi.${var.domain}"]
}

data "aws_route53_zone" "names" {
  count = var.dns_zone == "" ? 0 : 1
  name  = var.dns_zone
}

resource "aws_route53_record" "names" {
  for_each = var.dns_zone == "" ? toset([]) : toset(local.names)
  zone_id  = data.aws_route53_zone.names[0].zone_id
  name     = each.key
  type     = "A"
  ttl      = 300
  records  = [aws_eip.server.public_ip]
}
