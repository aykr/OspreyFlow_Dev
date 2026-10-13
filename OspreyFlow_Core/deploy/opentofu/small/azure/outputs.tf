# What the install needs next, and what the client points their DNS name at. The same names as the
# AWS module's where the two mean the same thing.

output "address" {
  description = "Point the domain's A records (the name, id. and bi.) here."
  value       = azurerm_public_ip.server.ip_address
}

output "domain" {
  value = var.domain
}

output "database_host" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "database_password_secret" {
  description = "Where Key Vault keeps the database password."
  value       = azurerm_key_vault_secret.database_password.versionless_id
}

output "media_account" {
  value = azurerm_storage_account.media.name
}

output "media_container" {
  value = azurerm_storage_container.media.name
}

output "key_vault" {
  description = "The vault's name: the first administrator's code is its first-admin-code secret."
  value       = azurerm_key_vault.main.name
}

output "install_answers" {
  description = "What the server's first boot installs from (no secret in it)."
  value       = yamlencode(local.answers)
}

output "server" {
  value = azurerm_linux_virtual_machine.server.id
}
