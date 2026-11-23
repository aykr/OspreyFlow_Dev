# Decision 4: RDS PostgreSQL 16, the application's database `ospreyflow` (the report
# mart a schema in it, osprey_reports, as on Small), encrypted, reached over TLS. The
# gateway's `litellm` and, with Superset on, Superset's `superset` are made on it at
# start by their own start-up, as on a cluster (ADR-148 Amendment 11): three databases
# on the one instance.

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.namespace}-postgres"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "postgres" {
  name   = "${var.namespace}-postgres"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["172.20.0.0/16"]
  }
}

resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${var.namespace}-postgres"
  family = "postgres16"

  parameter {
    name         = "max_connections"
    value        = "1000"
    apply_method = "pending-reboot"
  }
}

resource "aws_db_instance" "postgres" {
  identifier                = "${var.namespace}-postgres"
  engine                    = "postgres"
  engine_version            = "16"
  instance_class            = "db.t4g.large"
  allocated_storage         = 20
  max_allocated_storage     = 100
  storage_encrypted         = true
  multi_az                  = false
  db_name                   = "ospreyflow"
  username                  = "osprey"
  password                  = random_password.postgres.result
  db_subnet_group_name      = aws_db_subnet_group.postgres.name
  parameter_group_name      = aws_db_parameter_group.postgres.name
  vpc_security_group_ids    = [aws_security_group.postgres.id]
  backup_retention_period   = 35
  deletion_protection       = false
  skip_final_snapshot       = true
  final_snapshot_identifier = null
  ca_cert_identifier        = "rds-ca-rsa2048-g1"
}

resource "kubernetes_secret" "rds_postgresql_instance_output" {
  metadata {
    name      = "rds-postgresql-instance-output"
    namespace = var.namespace
  }

  data = {
    rds_instance_address = aws_db_instance.postgres.address
    rds_instance_port    = tostring(aws_db_instance.postgres.port)
    database_username    = aws_db_instance.postgres.username
    database_password    = random_password.postgres.result
    database_name        = aws_db_instance.postgres.db_name
  }
}
