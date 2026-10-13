# What the install needs next, and what the client points their DNS name at.

output "address" {
  description = "Point the domain's A record here."
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

output "media_bucket" {
  value = aws_s3_bucket.media.bucket
}

output "deployment_secret" {
  value = aws_secretsmanager_secret.deployment.arn
}

output "server" {
  description = "Reach it with: aws ssm start-session --target <this>"
  value       = aws_instance.server.id
}
