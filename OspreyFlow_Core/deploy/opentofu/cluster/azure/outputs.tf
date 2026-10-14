# What the operator and the cluster install need from this module, under the AWS module's names
# where the two mean the same thing. No secret is an output: each is named, and read from Key Vault.

output "cluster_name" {
  description = "The AKS cluster; `az aks get-credentials --name <this> --resource-group <resource_group>` then `kubelogin convert-kubeconfig -l azurecli` points kubectl at it."
  value       = azurerm_kubernetes_cluster.main.name
}

output "resource_group" {
  description = "The resource group everything is in."
  value       = azurerm_resource_group.main.name
}

output "region" {
  description = "The region everything is in."
  value       = var.region
}

output "key_vault" {
  description = "The vault holding the three secrets below."
  value       = azurerm_key_vault.main.name
}

output "database_password_secret" {
  description = "Key Vault: the database password, for OSPREY_POSTGRES_PASSWORD."
  value       = azurerm_key_vault_secret.install["database-password"].versionless_id
}

output "valkey_token_secret" {
  description = "Key Vault: the cache's access key, for VALKEY_PASSWORD."
  value       = azurerm_key_vault_secret.install["valkey-token"].versionless_id
}

output "media_key_secret" {
  description = "Key Vault: the Blob account's key, for AZURE_STORAGE_KEY."
  value       = azurerm_key_vault_secret.install["media-storage-key"].versionless_id
}

output "install_answers" {
  description = "What `ospreyflow install --mode enterprise --config` installs from (no secret in it)."
  value       = yamlencode(local.answers)
}
