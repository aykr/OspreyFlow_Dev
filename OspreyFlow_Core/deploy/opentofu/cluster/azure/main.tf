# Enterprise on Azure (ADR-114 decisions 9 and 10, Amendment 18): an AKS cluster for the chart, with
# the cloud's managed services underneath — Azure Database for PostgreSQL (flexible server), Azure
# Cache for Redis, Blob Storage for media and Key Vault — and Azure Files for the one volume every
# Conduit shares. The same shape as the AWS module (decision 10).
#
# Choices made here, recorded in ADR-114 Amendment 18:
# - the cluster's API answers only the addresses in `api_cidrs`; the nodes have no public addresses;
#   it has no local accounts, so every sign-in to it is an Entra ID one (`kubelogin`);
# - Azure network policy is switched on, or the chart's NetworkPolicies would be accepted and
#   enforced by nothing;
# - search runs in the cluster (decision 9: Azure has no managed OpenSearch), and so do the
#   S3-protocol stores, as on Small (Amendment 10 point 2); media goes to Blob;
# - the database, the cache and the Blob account are reached only through the virtual network
#   (a delegated subnet, and private endpoints with their private DNS zones);
# - the two storage classes the chart names are made here (`ospreyflow-volumes` on zone-redundant
#   premium disks, `ospreyflow-shared` on premium Azure Files behind a private endpoint);
# - the database password is generated here and so is in this state (the flexible server takes a
#   password, not a managed secret), as are the cache's and the Blob account's keys; all three are
#   copied into Key Vault for the install — the state must be kept as a secret.

terraform {
  required_version = ">= 1.10"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.14"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.33"
    }
  }
}

# The subscription comes from `ARM_SUBSCRIPTION_ID` (or the signed-in `az` command line).
provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}

# The storage classes are made through the cluster's own API, as the operator's Entra ID identity:
# the cluster has no local accounts. 6dae42f8-… is AKS's own Entra ID server application.
provider "kubernetes" {
  host                   = azurerm_kubernetes_cluster.main.kube_config[0].host
  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].cluster_ca_certificate)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "kubelogin"
    args        = ["get-token", "--login", "azurecli", "--server-id", "6dae42f8-4368-4678-94ff-3960e28e3630"]
  }
}

locals {
  node_size  = { small = "Standard_E4s_v5", medium = "Standard_E8s_v5", large = "Standard_E16s_v5" }[var.size]
  node_count = { small = 3, medium = 4, large = 6 }[var.size]
  db_sku = {
    small = "GP_Standard_D2ds_v5", medium = "GP_Standard_D4ds_v5", large = "GP_Standard_D8ds_v5"
  }[var.size]
  cache = {
    small  = { sku = "Standard", family = "C", capacity = 2 }
    medium = { sku = "Premium", family = "P", capacity = 1 }
    large  = { sku = "Premium", family = "P", capacity = 2 }
  }[var.size]
  compact = substr(replace(var.name, "-", ""), 0, 16)
  tags    = { "ospreyflow-deployment" = var.name }
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_resource_group" "main" {
  name     = var.name
  location = var.region
  tags     = local.tags
}

# --- network ---------------------------------------------------------------------------------

resource "azurerm_virtual_network" "main" {
  name                = var.name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  address_space       = ["10.42.0.0/16"]
}

# Pods take overlay addresses, not the network's, so the nodes' subnet need hold only the nodes.
resource "azurerm_subnet" "nodes" {
  name                 = "nodes"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.42.0.0/22"]
}

resource "azurerm_subnet" "database" {
  name                 = "database"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.42.8.0/24"]
  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "endpoints" {
  name                 = "endpoints"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.42.9.0/24"]
}

# One private DNS zone for each service reached through the network, each linked to it.
locals {
  private_zones = {
    postgres = "${var.name}.private.postgres.database.azure.com"
    redis    = "privatelink.redis.cache.windows.net"
    blob     = "privatelink.blob.core.windows.net"
  }
}

resource "azurerm_private_dns_zone" "private" {
  for_each            = local.private_zones
  name                = each.value
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "private" {
  for_each              = local.private_zones
  name                  = "${var.name}-${each.key}"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.private[each.key].name
  virtual_network_id    = azurerm_virtual_network.main.id
}

# --- the cluster ---------------------------------------------------------------------------------

resource "azurerm_kubernetes_cluster" "main" {
  name                   = var.name
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  dns_prefix             = var.name
  kubernetes_version     = var.kubernetes_version
  sku_tier               = "Standard"
  local_account_disabled = true
  azure_active_directory_role_based_access_control {
    tenant_id          = data.azurerm_client_config.current.tenant_id
    azure_rbac_enabled = true
  }
  api_server_access_profile {
    authorized_ip_ranges = var.api_cidrs
  }
  # The system pool runs Kubernetes' own add-ons and nothing else; the deployment runs on `main`.
  default_node_pool {
    name                         = "system"
    vm_size                      = "Standard_D4s_v5"
    node_count                   = 3
    zones                        = ["1", "2", "3"]
    vnet_subnet_id               = azurerm_subnet.nodes.id
    node_public_ip_enabled       = false
    only_critical_addons_enabled = true
    upgrade_settings {
      max_surge = "33%"
    }
  }
  identity {
    type = "SystemAssigned"
  }
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "azure"
    pod_cidr            = "10.244.0.0/16"
    service_cidr        = "172.16.0.0/16"
    dns_service_ip      = "172.16.0.10"
  }
  storage_profile {
    disk_driver_enabled = true
    file_driver_enabled = true
  }
  tags = local.tags
}

resource "azurerm_kubernetes_cluster_node_pool" "main" {
  name                   = "main"
  kubernetes_cluster_id  = azurerm_kubernetes_cluster.main.id
  vm_size                = local.node_size
  node_count             = local.node_count
  zones                  = ["1", "2", "3"]
  vnet_subnet_id         = azurerm_subnet.nodes.id
  node_public_ip_enabled = false
  os_disk_size_gb        = 128
  upgrade_settings {
    max_surge = "1"
  }
  tags = local.tags
}

# The cluster's own identity joins the nodes' subnet, which is not in the resource group it manages.
resource "azurerm_role_assignment" "cluster_joins_subnet" {
  scope                = azurerm_subnet.nodes.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_kubernetes_cluster.main.identity[0].principal_id
}

# Whoever runs this administers the cluster (it makes the storage classes and installs the chart).
resource "azurerm_role_assignment" "deployer_administers_cluster" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "kubernetes_storage_class_v1" "volumes" {
  metadata {
    name = "ospreyflow-volumes"
  }
  storage_provisioner    = "disk.csi.azure.com"
  reclaim_policy         = "Retain"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true
  parameters = {
    # Zone-redundant, so a store's volume follows its pod to another zone.
    skuName = "Premium_ZRS"
  }
  depends_on = [azurerm_role_assignment.deployer_administers_cluster]
}

resource "kubernetes_storage_class_v1" "shared" {
  metadata {
    name = "ospreyflow-shared"
  }
  storage_provisioner    = "file.csi.azure.com"
  reclaim_policy         = "Retain"
  allow_volume_expansion = true
  parameters = {
    skuName             = "Premium_LRS"
    networkEndpointType = "privateEndpoint"
  }
  # The deployment's processes run as 1000:1000 (the same owner as the EFS class on AWS).
  mount_options = ["uid=1000", "gid=1000", "dir_mode=0770", "file_mode=0660", "mfsymlinks", "nobrl", "cache=strict"]
  depends_on    = [azurerm_role_assignment.deployer_administers_cluster]
}

# --- the managed stores ------------------------------------------------------------------------

resource "random_password" "database" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "${var.name}-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "16"
  sku_name                      = local.db_sku
  storage_mb                    = 131072
  backup_retention_days         = var.backup_days
  delegated_subnet_id           = azurerm_subnet.database.id
  private_dns_zone_id           = azurerm_private_dns_zone.private["postgres"].id
  public_network_access_enabled = false
  administrator_login           = "osprey"
  administrator_password        = random_password.database.result
  zone                          = "1"
  high_availability {
    mode                      = "ZoneRedundant"
    standby_availability_zone = "2"
  }
  depends_on = [azurerm_private_dns_zone_virtual_network_link.private]
  lifecycle {
    ignore_changes = [zone, high_availability[0].standby_availability_zone]
  }
}

# Neither `tofu destroy` nor anyone in the portal takes the database with it unasked: Azure refuses
# to delete a locked resource, and the lock is lifted by hand to mean it (as RDS's deletion
# protection is on AWS).
resource "azurerm_management_lock" "database" {
  name       = "${var.name}-database"
  scope      = azurerm_postgresql_flexible_server.main.id
  lock_level = "CanNotDelete"
  notes      = "The deployment's database (ADR-114 Amendment 18)."
}

resource "azurerm_postgresql_flexible_server_database" "ospreyflow" {
  name      = "ospreyflow"
  server_id = azurerm_postgresql_flexible_server.main.id
}

resource "azurerm_redis_cache" "valkey" {
  name                          = "${var.name}-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  sku_name                      = local.cache.sku
  family                        = local.cache.family
  capacity                      = local.cache.capacity
  non_ssl_port_enabled          = false
  minimum_tls_version           = "1.2"
  public_network_access_enabled = false
  redis_version                 = "6"
}

resource "azurerm_private_endpoint" "valkey" {
  name                = "${var.name}-cache"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.endpoints.id
  private_service_connection {
    name                           = "cache"
    private_connection_resource_id = azurerm_redis_cache.valkey.id
    subresource_names              = ["redisCache"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "cache"
    private_dns_zone_ids = [azurerm_private_dns_zone.private["redis"].id]
  }
}

resource "azurerm_storage_account" "media" {
  name                            = "${local.compact}${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "ZRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = false
  # The Blob media adapter signs with the account's Shared Key (`adapters/media_blob`).
  shared_access_key_enabled = true
  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = var.backup_days
    }
  }
}

resource "azurerm_private_endpoint" "media" {
  name                = "${var.name}-media"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.endpoints.id
  private_service_connection {
    name                           = "media"
    private_connection_resource_id = azurerm_storage_account.media.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "media"
    private_dns_zone_ids = [azurerm_private_dns_zone.private["blob"].id]
  }
}

# The account takes no public traffic, so the container is made through Azure's own API, not the
# account's endpoint (which would need the network this is run from to reach it).
resource "azurerm_storage_container" "media" {
  name                  = "ospreyflow-media"
  storage_account_id    = azurerm_storage_account.media.id
  container_access_type = "private"
}

# --- what the install reads ----------------------------------------------------------------------

resource "azurerm_key_vault" "main" {
  name                       = "${local.compact}${random_string.suffix.result}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 30
  # Read from the operator's network only, as the cluster's API is.
  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
    ip_rules       = var.api_cidrs
  }
}

resource "azurerm_role_assignment" "deployer_writes_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "install" {
  for_each = {
    "database-password" = random_password.database.result
    "valkey-token"      = azurerm_redis_cache.valkey.primary_access_key
    "media-storage-key" = azurerm_storage_account.media.primary_access_key
  }
  name         = each.key
  value        = each.value
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_writes_secrets]
}

locals {
  # The answers `ospreyflow install --mode enterprise` installs from: no secret in it — the database
  # password, the cache's key and the Blob account's key are read from Key Vault by the operator's
  # own identity. No `object_store` and no `search`: on Azure both run in the cluster.
  answers = {
    mode = "enterprise"
    cloud = merge(
      { provider = "azure", region = var.region, domain = var.domain },
      var.admin_email == "" ? {} : { admin_email = var.admin_email },
    )
    cluster = {
      namespace            = var.namespace
      storage_class        = kubernetes_storage_class_v1.volumes.metadata[0].name
      shared_storage_class = kubernetes_storage_class_v1.shared.metadata[0].name
    }
    external = {
      postgres = {
        host     = azurerm_postgresql_flexible_server.main.fqdn
        port     = 5432
        database = "ospreyflow"
        user     = "osprey"
        sslmode  = "require"
      }
      valkey = {
        host = azurerm_redis_cache.valkey.hostname
        port = azurerm_redis_cache.valkey.ssl_port
        tls  = true
      }
      media = {
        blob_account   = azurerm_storage_account.media.name
        blob_container = azurerm_storage_container.media.name
      }
    }
  }
}
