# Enterprise on AWS (ADR-114 decisions 9 and 10, Amendment 18): an EKS cluster for the chart, with the
# cloud's managed services underneath — RDS for PostgreSQL, ElastiCache for Valkey, S3, Amazon
# OpenSearch Service — and EFS for the one volume every Conduit shares.
#
# Choices made here, recorded in ADR-114 Amendment 18:
# - the cluster's API answers only the addresses in `api_cidrs`; the nodes are in private subnets
#   and reach out through one NAT gateway;
# - the VPC CNI's network-policy engine is switched on, or the chart's NetworkPolicies would be
#   accepted and enforced by nothing;
# - pods reach S3 as the node does (its role, the instance metadata hop limit raised to 2), as
#   Small's server does (`credentials: instance`);
# - the two storage classes the chart names are made here (`ospreyflow-volumes` on EBS gp3,
#   `ospreyflow-shared` on EFS), since EKS has neither;
# - the database password is kept by Secrets Manager (RDS-managed, never in this state); the Valkey
#   token is made here and so is in this state, and copied into Secrets Manager for the install —
#   the state must be kept as a secret.

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
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.33"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { "ospreyflow:deployment" = var.name }
  }
}

# The storage classes are made through the cluster's own API, as the operator's AWS identity.
provider "kubernetes" {
  host                   = aws_eks_cluster.main.endpoint
  cluster_ca_certificate = base64decode(aws_eks_cluster.main.certificate_authority[0].data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", aws_eks_cluster.main.name, "--region", var.region]
  }
}

locals {
  node_type  = { small = "m6i.2xlarge", medium = "r6i.2xlarge", large = "r6i.4xlarge" }[var.size]
  node_count = { small = 3, medium = 4, large = 6 }[var.size]
  db_class   = { small = "db.m6g.large", medium = "db.m6g.xlarge", large = "db.m6g.2xlarge" }[var.size]
  cache_type = { small = "cache.t4g.medium", medium = "cache.m6g.large", large = "cache.m6g.xlarge" }[var.size]
  search_type = {
    small = "m6g.large.search", medium = "m6g.xlarge.search", large = "r6g.xlarge.search"
  }[var.size]
  zones = slice(data.aws_availability_zones.here.names, 0, 3)
}

data "aws_availability_zones" "here" {
  state = "available"
}

data "aws_caller_identity" "here" {}

# --- network ---------------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "public" {
  count                   = 3
  vpc_id                  = aws_vpc.main.id
  availability_zone       = local.zones[count.index]
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  map_public_ip_on_launch = false
  tags                    = { "kubernetes.io/role/elb" = "1" }
}

resource "aws_subnet" "private" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  availability_zone = local.zones[count.index]
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 4, count.index + 1)
  tags              = { "kubernetes.io/role/internal-elb" = "1" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 3
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  domain = "vpc"
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
}

resource "aws_route_table_association" "private" {
  count          = 3
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# --- the cluster -------------------------------------------------------------------------------

data "aws_iam_policy_document" "assume_eks" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cluster" {
  name               = "${var.name}-cluster"
  assume_role_policy = data.aws_iam_policy_document.assume_eks.json
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_kms_key" "secrets" {
  description         = "${var.name}: Kubernetes Secrets at rest"
  enable_key_rotation = true
}

resource "aws_eks_cluster" "main" {
  name     = var.name
  version  = var.kubernetes_version
  role_arn = aws_iam_role.cluster.arn
  vpc_config {
    subnet_ids              = concat(aws_subnet.private[*].id, aws_subnet.public[*].id)
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.api_cidrs
  }
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }
  encryption_config {
    resources = ["secrets"]
    provider {
      key_arn = aws_kms_key.secrets.arn
    }
  }
  depends_on = [aws_iam_role_policy_attachment.cluster]
}

data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "nodes" {
  name               = "${var.name}-nodes"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
}

resource "aws_iam_role_policy_attachment" "nodes" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
  ])
  role       = aws_iam_role.nodes.name
  policy_arn = each.value
}

# Pods reach S3 as the node does (05 §3a's `credentials: instance`).
data "aws_iam_policy_document" "nodes_s3" {
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [for store in aws_s3_bucket.store : store.arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [for store in aws_s3_bucket.store : "${store.arn}/*"]
  }
}

resource "aws_iam_role_policy" "nodes_s3" {
  role   = aws_iam_role.nodes.id
  policy = data.aws_iam_policy_document.nodes_s3.json
}

resource "aws_launch_template" "nodes" {
  name_prefix = "${var.name}-nodes-"
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2 # one hop for the node, one for a pod
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size = 100
      volume_type = "gp3"
      encrypted   = true
    }
  }
}

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.name}-main"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = aws_subnet.private[*].id
  instance_types  = [local.node_type]
  scaling_config {
    desired_size = local.node_count
    min_size     = local.node_count
    max_size     = local.node_count * 2
  }
  launch_template {
    id      = aws_launch_template.nodes.id
    version = aws_launch_template.nodes.latest_version
  }
  depends_on = [aws_iam_role_policy_attachment.nodes]
}

# --- the add-ons: networking that enforces policies, and the two storage drivers -------------

data "tls_certificate" "oidc" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "main" {
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.oidc.certificates[0].sha1_fingerprint]
}

locals {
  oidc = replace(aws_iam_openid_connect_provider.main.url, "https://", "")
  drivers = {
    ebs = { account = "ebs-csi-controller-sa", policy = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy" }
    efs = { account = "efs-csi-controller-sa", policy = "arn:aws:iam::aws:policy/service-role/AmazonEFSCSIDriverPolicy" }
  }
}

data "aws_iam_policy_document" "assume_driver" {
  for_each = local.drivers
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.main.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc}:sub"
      values   = ["system:serviceaccount:kube-system:${each.value.account}"]
    }
  }
}

resource "aws_iam_role" "driver" {
  for_each           = local.drivers
  name               = "${var.name}-${each.key}-csi"
  assume_role_policy = data.aws_iam_policy_document.assume_driver[each.key].json
}

resource "aws_iam_role_policy_attachment" "driver" {
  for_each   = local.drivers
  role       = aws_iam_role.driver[each.key].name
  policy_arn = each.value.policy
}

resource "aws_eks_addon" "vpc_cni" {
  cluster_name = aws_eks_cluster.main.name
  addon_name   = "vpc-cni"
  # The chart's NetworkPolicies (05 §3b) are enforced only with this on.
  configuration_values = jsonencode({ enableNetworkPolicy = "true" })
}

resource "aws_eks_addon" "ebs" {
  cluster_name             = aws_eks_cluster.main.name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = aws_iam_role.driver["ebs"].arn
  depends_on               = [aws_eks_node_group.main]
}

resource "aws_eks_addon" "efs" {
  cluster_name             = aws_eks_cluster.main.name
  addon_name               = "aws-efs-csi-driver"
  service_account_role_arn = aws_iam_role.driver["efs"].arn
  depends_on               = [aws_eks_node_group.main]
}

# --- the shared volume (EFS) and the two storage classes the chart names ---------------------

resource "aws_security_group" "efs" {
  name   = "${var.name}-efs"
  vpc_id = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "efs_from_cluster" {
  security_group_id            = aws_security_group.efs.id
  referenced_security_group_id = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 2049
  to_port                      = 2049
}

resource "aws_efs_file_system" "shared" {
  encrypted        = true
  performance_mode = "generalPurpose"
  throughput_mode  = "elastic"
}

resource "aws_efs_mount_target" "shared" {
  count           = 3
  file_system_id  = aws_efs_file_system.shared.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

resource "kubernetes_storage_class_v1" "volumes" {
  metadata {
    name = "ospreyflow-volumes"
  }
  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Retain"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true
  parameters = {
    type      = "gp3"
    encrypted = "true"
  }
  depends_on = [aws_eks_addon.ebs]
}

resource "kubernetes_storage_class_v1" "shared" {
  metadata {
    name = "ospreyflow-shared"
  }
  storage_provisioner = "efs.csi.aws.com"
  reclaim_policy      = "Retain"
  parameters = {
    provisioningMode = "efs-ap"
    fileSystemId     = aws_efs_file_system.shared.id
    directoryPerms   = "770"
    uid              = "1000"
    gid              = "1000"
  }
  depends_on = [aws_eks_addon.efs, aws_efs_mount_target.shared]
}

# --- the managed stores ------------------------------------------------------------------------

locals {
  cluster_sg = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
}

resource "aws_security_group" "stores" {
  name   = "${var.name}-stores"
  vpc_id = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "stores_from_cluster" {
  for_each                     = { postgres = 5432, valkey = 6379, search = 443 }
  security_group_id            = aws_security_group.stores.id
  referenced_security_group_id = local.cluster_sg
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "postgres" {
  identifier                  = var.name
  engine                      = "postgres"
  engine_version              = "16"
  instance_class              = local.db_class
  allocated_storage           = 100
  max_allocated_storage       = 1000
  storage_type                = "gp3"
  storage_encrypted           = true
  multi_az                    = true
  db_name                     = "ospreyflow"
  username                    = "osprey"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.main.name
  vpc_security_group_ids      = [aws_security_group.stores.id]
  publicly_accessible         = false
  backup_retention_period     = var.backup_days
  deletion_protection         = true
  skip_final_snapshot         = false
  final_snapshot_identifier   = "${var.name}-final"
  copy_tags_to_snapshot       = true
  auto_minor_version_upgrade  = true
}

resource "aws_elasticache_subnet_group" "main" {
  name       = var.name
  subnet_ids = aws_subnet.private[*].id
}

resource "random_password" "valkey" {
  length  = 40
  special = false # ElastiCache refuses some punctuation in a token
}

resource "aws_elasticache_replication_group" "valkey" {
  replication_group_id       = var.name
  description                = "${var.name}: the Conduit's working-set cache and job queue"
  engine                     = "valkey"
  engine_version             = "8.0"
  node_type                  = local.cache_type
  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.stores.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.valkey.result
  snapshot_retention_limit   = 7
}

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

resource "aws_opensearch_domain" "search" {
  count          = var.search ? 1 : 0
  domain_name    = var.name
  engine_version = "OpenSearch_2.17"
  cluster_config {
    instance_type          = local.search_type
    instance_count         = 2
    zone_awareness_enabled = true
    zone_awareness_config {
      availability_zone_count = 2
    }
  }
  ebs_options {
    ebs_enabled = true
    volume_size = 100
    volume_type = "gp3"
  }
  vpc_options {
    subnet_ids         = slice(aws_subnet.private[*].id, 0, 2)
    security_group_ids = [aws_security_group.stores.id]
  }
  encrypt_at_rest {
    enabled = true
  }
  node_to_node_encryption {
    enabled = true
  }
  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }
  # Reached only inside the VPC, through the stores' security group (the cluster's alone): the
  # network is the boundary, so the domain's own policy admits a caller that gets there.
  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "*" }
      Action    = "es:ESHttp*"
      Resource  = "arn:aws:es:${var.region}:${data.aws_caller_identity.here.account_id}:domain/${var.name}/*"
    }]
  })
}

# --- what the install reads ----------------------------------------------------------------------

resource "aws_secretsmanager_secret" "valkey" {
  name                    = "${var.name}/valkey-token"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "valkey" {
  secret_id     = aws_secretsmanager_secret.valkey.id
  secret_string = random_password.valkey.result
}

locals {
  # The answers `ospreyflow install --mode enterprise` installs from: no secret in it — the database
  # password and the Valkey token are read from Secrets Manager by the operator's own identity.
  answers = {
    mode = "enterprise"
    cloud = merge(
      { provider = "aws", region = var.region, domain = var.domain },
      var.admin_email == "" ? {} : { admin_email = var.admin_email },
    )
    cluster = {
      namespace            = var.namespace
      storage_class        = kubernetes_storage_class_v1.volumes.metadata[0].name
      shared_storage_class = kubernetes_storage_class_v1.shared.metadata[0].name
    }
    external = merge(
      {
        postgres = {
          host     = aws_db_instance.postgres.address
          port     = 5432
          database = "ospreyflow"
          user     = "osprey"
          sslmode  = "require"
        }
        valkey = {
          host = aws_elasticache_replication_group.valkey.primary_endpoint_address
          port = 6379
          tls  = true
        }
        object_store = {
          endpoint      = "s3.${var.region}.amazonaws.com"
          region        = var.region
          credentials   = "instance"
          bucket_prefix = local.bucket_prefix
        }
      },
      var.search ? { search = { url = "https://${aws_opensearch_domain.search[0].endpoint}" } } : {},
    )
  }
}
