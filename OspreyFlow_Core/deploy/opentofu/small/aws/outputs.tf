# What the install needs next, and what the client points their DNS name at.

output "address" {
  description = "Point the domain's A records (the name, id. and bi.) here."
  value       = aws_eip.server.public_ip
}

output "domain" {
  value = var.domain
}

output "database_host" {
  value = aws_db_instance.postgres.address
}

output "database_password_secret" {
  description = "Where Secrets Manager keeps the database password (never in this state)."
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "bucket_prefix" {
  value = local.bucket_prefix
}

output "region" {
  value = var.region
}

output "first_admin_secret" {
  description = "Where the first boot leaves the first administrator's one-time code."
  value       = aws_secretsmanager_secret.first_admin.arn
}

output "deployment_secret" {
  value = aws_secretsmanager_secret.deployment.arn
}

output "server" {
  description = "Reach it with: aws ssm start-session --target <this>"
  value       = aws_instance.server.id
}

output "install_answers" {
  description = "What the server's first boot installs from (no secret in it)."
  value       = yamlencode(local.answers)
}
