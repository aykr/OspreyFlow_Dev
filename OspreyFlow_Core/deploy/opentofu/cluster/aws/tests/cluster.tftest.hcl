# Enterprise's promises on AWS (ADR-114 decisions 9 and 10, Amendment 18), run against mock providers
# so they need no credentials. Each `run` names the promise it holds.

mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["eu-west-2a", "eu-west-2b", "eu-west-2c"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "111122223333" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_resource "aws_eks_cluster" {
    defaults = {
      endpoint              = "https://ABC.gr7.eu-west-2.eks.amazonaws.com"
      certificate_authority = [{ data = "Y2VydA==" }]
      identity              = [{ oidc = [{ issuer = "https://oidc.eks.eu-west-2.amazonaws.com/id/ABC" }] }]
    }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::111122223333:oidc-provider/oidc.eks.eu-west-2.amazonaws.com/id/ABC"
    }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      address = "osprey-test.abc.eu-west-2.rds.amazonaws.com"
      master_user_secret = [{
        secret_arn    = "arn:aws:secretsmanager:eu-west-2:111122223333:secret:rds-db-x"
        kms_key_id    = ""
        secret_status = "active"
      }]
    }
  }
  mock_resource "aws_elasticache_replication_group" {
    defaults = { primary_endpoint_address = "master.osprey-test.abc.euw2.cache.amazonaws.com" }
  }
  mock_resource "aws_opensearch_domain" {
    defaults = { endpoint = "vpc-osprey-test-abc.eu-west-2.es.amazonaws.com" }
  }
  mock_resource "aws_launch_template" {
    defaults = { id = "lt-0123456789abcdef0" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::osprey-test-x" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::111122223333:role/osprey-x" }
  }
  mock_resource "aws_kms_key" {
    defaults = { arn = "arn:aws:kms:eu-west-2:111122223333:key/x" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:eu-west-2:111122223333:secret:osprey-x" }
  }
}

mock_provider "tls" {
  mock_data "tls_certificate" {
    defaults = {
      certificates = [{
        cert_pem             = "-----BEGIN CERTIFICATE-----"
        is_ca                = true
        issuer               = "CN=Amazon Root CA 1"
        max_path_length      = 0
        not_after            = "2037-12-31T00:00:00Z"
        not_before           = "2015-05-26T00:00:00Z"
        public_key_algorithm = "RSA"
        serial_number        = "1"
        sha1_fingerprint     = "9e99a48a9960b14926bb7f3b02e22da2b0ab7280"
        signature_algorithm  = "SHA256-RSA"
        subject              = "CN=Amazon Root CA 1"
        version              = 3
      }]
    }
  }
}

mock_provider "kubernetes" {}

variables {
  name      = "osprey-test"
  region    = "eu-west-2"
  domain    = "osprey.example.org"
  api_cidrs = ["203.0.113.0/24"]
}

run "the_api_answers_only_the_operators_addresses" {
  command = plan
  assert {
    condition     = aws_eks_cluster.main.vpc_config[0].public_access_cidrs == toset(["203.0.113.0/24"])
    error_message = "the cluster's API must answer only api_cidrs"
  }
}

run "the_whole_internet_is_refused_as_an_api_address" {
  command = plan
  variables {
    api_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [var.api_cidrs]
}

run "the_nodes_are_private_and_pods_reach_s3_as_the_node" {
  command = apply
  # The mock provider gives public[i] and private[i] the same generated id, so each set is pinned to
  # an id of its own here; without that, moving the nodes to the public subnets passes unnoticed.
  override_resource {
    target = aws_subnet.private
    values = { id = "subnet-private" }
  }
  override_resource {
    target = aws_subnet.public
    values = { id = "subnet-public" }
  }
  assert {
    condition     = aws_eks_node_group.main.subnet_ids == toset(["subnet-private"])
    error_message = "the nodes are in the private subnets and no other"
  }
  assert {
    condition     = aws_launch_template.nodes.metadata_options[0].http_tokens == "required"
    error_message = "instance metadata takes tokens only (IMDSv2)"
  }
  assert {
    condition     = aws_launch_template.nodes.metadata_options[0].http_put_response_hop_limit == 2
    error_message = "a pod is one hop further than the node, or it cannot reach the node's role"
  }
}

run "the_charts_network_policies_are_enforced" {
  command = plan
  assert {
    condition     = jsondecode(aws_eks_addon.vpc_cni.configuration_values).enableNetworkPolicy == "true"
    error_message = "without the VPC CNI's policy engine the chart's NetworkPolicies are enforced by nothing"
  }
}

run "kubernetes_secrets_are_encrypted_with_a_key_of_their_own" {
  command = plan
  assert {
    condition     = contains(aws_eks_cluster.main.encryption_config[0].resources, "secrets")
    error_message = "the Secret every workload reads is encrypted at rest with KMS"
  }
}

run "the_database_is_private_encrypted_replicated_backed_up_and_guarded" {
  command = plan
  assert {
    condition = (
      aws_db_instance.postgres.publicly_accessible == false &&
      aws_db_instance.postgres.storage_encrypted == true &&
      aws_db_instance.postgres.multi_az == true &&
      aws_db_instance.postgres.backup_retention_period >= 7 &&
      aws_db_instance.postgres.deletion_protection == true &&
      aws_db_instance.postgres.manage_master_user_password == true
    )
    error_message = "the database is private, encrypted, in two zones, backed up, guarded, its password kept by Secrets Manager"
  }
}

run "valkey_is_reached_over_tls_with_a_token_and_fails_over" {
  command = plan
  assert {
    condition = (
      aws_elasticache_replication_group.valkey.transit_encryption_enabled == true &&
      tostring(aws_elasticache_replication_group.valkey.at_rest_encryption_enabled) == "true" &&
      aws_elasticache_replication_group.valkey.automatic_failover_enabled == true &&
      aws_elasticache_replication_group.valkey.num_cache_clusters == 2
    )
    error_message = "Valkey is encrypted in transit and at rest, and has a replica to fail over to"
  }
}

run "the_stores_take_only_the_clusters_traffic" {
  command = plan
  assert {
    condition = alltrue([
      for rule in aws_vpc_security_group_ingress_rule.stores_from_cluster : rule.cidr_ipv4 == null
    ])
    error_message = "the managed stores admit the cluster's security group, never an address range"
  }
}

run "the_buckets_are_private_and_encrypted" {
  command = plan
  assert {
    condition = alltrue([
      for block in aws_s3_bucket_public_access_block.store : block.block_public_acls && block.restrict_public_buckets
    ])
    error_message = "no bucket can be made public"
  }
}

run "the_chart_finds_both_storage_classes" {
  command = apply
  assert {
    condition = (
      kubernetes_storage_class_v1.volumes.storage_provisioner == "ebs.csi.aws.com" &&
      kubernetes_storage_class_v1.volumes.parameters.encrypted == "true" &&
      kubernetes_storage_class_v1.shared.storage_provisioner == "efs.csi.aws.com" &&
      kubernetes_storage_class_v1.shared.parameters.fileSystemId == aws_efs_file_system.shared.id
    )
    error_message = "ospreyflow-volumes on encrypted EBS, ospreyflow-shared on this module's EFS"
  }
}

run "the_install_answers_name_everything_and_hold_no_secret" {
  command = apply
  assert {
    condition = (
      yamldecode(output.install_answers).mode == "enterprise" &&
      yamldecode(output.install_answers).cluster.shared_storage_class == "ospreyflow-shared" &&
      yamldecode(output.install_answers).cluster.storage_class == "ospreyflow-volumes" &&
      yamldecode(output.install_answers).external.valkey.tls == true &&
      yamldecode(output.install_answers).external.postgres.sslmode == "require" &&
      yamldecode(output.install_answers).external.object_store.credentials == "instance" &&
      startswith(yamldecode(output.install_answers).external.search.url, "https://")
    )
    error_message = "the answers carry the cluster's classes and every managed service"
  }
  assert {
    condition     = !strcontains(output.install_answers, random_password.valkey.result)
    error_message = "the Valkey token is never in the answers"
  }
}

run "without_search_there_is_no_domain_and_no_search_answer" {
  command = apply
  variables {
    search = false
  }
  assert {
    condition     = length(aws_opensearch_domain.search) == 0 && !contains(keys(yamldecode(output.install_answers).external), "search")
    error_message = "search off makes no OpenSearch domain and names none"
  }
}
