# The Small deployment's promises on AWS (ADR-114 decisions 6, 8 and 10), planned against a mock
# provider so they run in CI with no credentials. Each `run` names the promise it holds.

mock_provider "aws" {
  mock_data "aws_ami" {
    defaults = { id = "ami-0123456789abcdef0" }
  }
  mock_data "aws_availability_zones" {
    defaults = { names = ["eu-west-2a", "eu-west-2b", "eu-west-2c"] }
  }
  mock_data "aws_region" {
    defaults = { name = "eu-west-2" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  # Planned values the provider would know only after an apply.
  mock_resource "aws_db_instance" {
    defaults = {
      master_user_secret = [{
        secret_arn    = "arn:aws:secretsmanager:eu-west-2:111122223333:secret:rds-db-x"
        kms_key_id    = ""
        secret_status = "active"
      }]
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::osprey-test-media-x" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:eu-west-2:111122223333:secret:osprey-x" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::111122223333:role/osprey-x" }
  }
  mock_resource "aws_instance" {
    defaults = { arn = "arn:aws:ec2:eu-west-2:111122223333:instance/i-0123456789abcdef0" }
  }
}

variables {
  name       = "osprey-test"
  region     = "eu-west-2"
  domain     = "osprey.example.org"
  repository = "https://example.org/ospreyflow.git"
}

run "only_the_web_ports_are_open_to_the_world" {
  command = plan
  assert {
    condition = alltrue([
      for rule in aws_vpc_security_group_ingress_rule.web : contains([80, 443], rule.from_port)
    ])
    error_message = "the server must take nothing from the internet but HTTP and HTTPS"
  }
  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.web) == 2
    error_message = "exactly two inbound rules: 80 for the certificate challenge, 443 for use"
  }
}

run "the_database_is_private_encrypted_backed_up_and_guarded" {
  command = plan
  assert {
    condition     = aws_db_instance.postgres.publicly_accessible == false
    error_message = "the database must not be reachable from the internet"
  }
  assert {
    condition     = aws_db_instance.postgres.storage_encrypted == true
    error_message = "the database must be encrypted at rest"
  }
  assert {
    condition     = aws_db_instance.postgres.backup_retention_period >= 7
    error_message = "the cloud keeps at least a week of database backups"
  }
  assert {
    condition     = aws_db_instance.postgres.deletion_protection == true
    error_message = "a tofu destroy must not take the database with it unasked"
  }
  assert {
    condition     = aws_db_instance.postgres.manage_master_user_password == true
    error_message = "the database password is kept by Secrets Manager, never in state"
  }
}

run "the_object_store_is_private_and_encrypted" {
  command = plan
  assert {
    condition = (
      aws_s3_bucket_public_access_block.media.block_public_acls &&
      aws_s3_bucket_public_access_block.media.block_public_policy &&
      aws_s3_bucket_public_access_block.media.ignore_public_acls &&
      aws_s3_bucket_public_access_block.media.restrict_public_buckets
    )
    error_message = "the media bucket must refuse every form of public access"
  }
}

run "the_server_recovers_itself_and_is_backed_up" {
  command = plan
  assert {
    condition     = endswith(one(aws_cloudwatch_metric_alarm.recover.alarm_actions), ":ec2:recover")
    error_message = "a failed host check must recover the instance"
  }
  assert {
    condition     = one(aws_backup_plan.daily.rule).lifecycle[0].delete_after >= 7
    error_message = "the server's own backups are kept at least a week"
  }
  assert {
    condition     = aws_instance.server.metadata_options[0].http_tokens == "required"
    error_message = "instance metadata only through IMDSv2"
  }
  assert {
    condition     = aws_instance.server.root_block_device[0].encrypted == true
    error_message = "the server's disk is encrypted"
  }
}

run "an_unknown_size_is_refused" {
  command = plan
  variables {
    size = "huge"
  }
  expect_failures = [var.size]
}

run "a_domain_that_is_not_a_name_is_refused" {
  command = plan
  variables {
    domain = "https://osprey.example.org/"
  }
  expect_failures = [var.domain]
}
