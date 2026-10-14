# What the operator and the cluster install need from this module. No secret is an output: the
# database password and the Valkey token are named, and read from Secrets Manager.

output "cluster_name" {
  description = "The EKS cluster; `aws eks update-kubeconfig --name <this> --region <region>` points kubectl at it."
  value       = aws_eks_cluster.main.name
}

output "region" {
  description = "The region everything is in."
  value       = var.region
}

output "database_password_secret" {
  description = "Secrets Manager: the database password (RDS keeps it), for OSPREY_POSTGRES_PASSWORD."
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "valkey_token_secret" {
  description = "Secrets Manager: the Valkey token, for VALKEY_PASSWORD."
  value       = aws_secretsmanager_secret.valkey.arn
}

output "shared_file_system" {
  description = "The EFS file system behind the ospreyflow-shared storage class."
  value       = aws_efs_file_system.shared.id
}

output "install_answers" {
  description = "What `ospreyflow install --mode enterprise --config` installs from (no secret in it)."
  value       = yamlencode(local.answers)
}
