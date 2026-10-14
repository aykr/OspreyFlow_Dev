# Enterprise's promises on Azure (ADR-114 decisions 9 and 10, Amendment 18), run against mock
# providers so they need no credentials. The same promises as the AWS module's, where Azure has them.

mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id = "00000000-0000-0000-0000-000000000001"
      object_id = "00000000-0000-0000-0000-000000000002"
    }
  }
  mock_resource "azurerm_resource_group" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test" }
  }
  mock_resource "azurerm_virtual_network" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Network/virtualNetworks/osprey-test" }
  }
  mock_resource "azurerm_subnet" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Network/virtualNetworks/osprey-test/subnets/nodes" }
  }
  mock_resource "azurerm_private_dns_zone" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Network/privateDnsZones/privatelink.example" }
  }
  mock_resource "azurerm_kubernetes_cluster" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.ContainerService/managedClusters/osprey-test"
      kube_config = [{
        host                   = "https://osprey-test.hcp.uksouth.azmk8s.io:443"
        cluster_ca_certificate = "Y2VydA=="
        client_certificate     = ""
        client_key             = ""
        username               = ""
        password               = ""
      }]
      identity = { principal_id = "00000000-0000-0000-0000-000000000003", tenant_id = "00000000-0000-0000-0000-000000000001" }
    }
  }
  mock_resource "azurerm_postgresql_flexible_server" {
    defaults = {
      id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.DBforPostgreSQL/flexibleServers/osprey-test-x"
      fqdn = "osprey-test-x.postgres.database.azure.com"
    }
  }
  mock_resource "azurerm_redis_cache" {
    defaults = {
      id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Cache/redis/osprey-test-x"
      hostname = "osprey-test-x.redis.cache.windows.net"
      ssl_port = 6380
    }
  }
  mock_resource "azurerm_storage_account" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Storage/storageAccounts/ospreytestx" }
  }
  mock_resource "azurerm_key_vault" {
    defaults = {
      id        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.KeyVault/vaults/ospreytestx"
      vault_uri = "https://ospreytestx.vault.azure.net/"
    }
  }
}

mock_provider "random" {}

mock_provider "kubernetes" {}

variables {
  name      = "osprey-test"
  region    = "uksouth"
  domain    = "osprey.example.org"
  api_cidrs = ["203.0.113.0/24"]
}

run "the_api_answers_only_the_operators_addresses" {
  command = plan
  assert {
    condition     = azurerm_kubernetes_cluster.main.api_server_access_profile[0].authorized_ip_ranges == toset(["203.0.113.0/24"])
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

run "every_sign_in_to_the_cluster_is_an_entra_id_one" {
  command = plan
  assert {
    condition = (
      azurerm_kubernetes_cluster.main.local_account_disabled == true &&
      azurerm_kubernetes_cluster.main.azure_active_directory_role_based_access_control[0].azure_rbac_enabled == true
    )
    error_message = "the cluster has no local accounts, and Azure RBAC decides who may do what in it"
  }
}

run "the_nodes_have_no_public_addresses_and_the_deployment_has_its_own_pool" {
  command = plan
  assert {
    condition = (
      azurerm_kubernetes_cluster.main.default_node_pool[0].node_public_ip_enabled == false &&
      azurerm_kubernetes_cluster_node_pool.main.node_public_ip_enabled == false
    )
    error_message = "no node has a public address"
  }
  assert {
    condition     = azurerm_kubernetes_cluster.main.default_node_pool[0].only_critical_addons_enabled == true
    error_message = "the system pool runs Kubernetes' own add-ons only"
  }
}

run "the_charts_network_policies_are_enforced" {
  command = plan
  assert {
    condition     = azurerm_kubernetes_cluster.main.network_profile[0].network_policy == "azure"
    error_message = "without a network-policy engine the chart's NetworkPolicies are enforced by nothing"
  }
}

run "the_database_is_private_replicated_backed_up_and_guarded" {
  command = plan
  assert {
    condition = (
      azurerm_postgresql_flexible_server.main.public_network_access_enabled == false &&
      azurerm_postgresql_flexible_server.main.high_availability[0].mode == "ZoneRedundant" &&
      azurerm_postgresql_flexible_server.main.backup_retention_days >= 7
    )
    error_message = "the database is private, in two zones and backed up"
  }
  assert {
    condition     = azurerm_management_lock.database.lock_level == "CanNotDelete"
    error_message = "the database cannot be deleted until its lock is lifted by hand"
  }
}

run "the_cache_is_reached_only_over_tls_and_only_through_the_network" {
  command = plan
  assert {
    condition = (
      azurerm_redis_cache.valkey.non_ssl_port_enabled == false &&
      azurerm_redis_cache.valkey.minimum_tls_version == "1.2" &&
      azurerm_redis_cache.valkey.public_network_access_enabled == false &&
      tolist(azurerm_private_endpoint.valkey.private_service_connection[0].subresource_names) == tolist(["redisCache"])
    )
    error_message = "the cache takes TLS only, and only from its private endpoint"
  }
}

run "media_is_private" {
  command = plan
  assert {
    condition = (
      azurerm_storage_account.media.public_network_access_enabled == false &&
      azurerm_storage_account.media.allow_nested_items_to_be_public == false &&
      azurerm_storage_container.media.container_access_type == "private" &&
      tolist(azurerm_private_endpoint.media.private_service_connection[0].subresource_names) == tolist(["blob"])
    )
    error_message = "the Blob account takes no public traffic and no container can be made public"
  }
}

run "the_secrets_are_read_from_the_operators_network_only" {
  command = plan
  assert {
    condition = (
      azurerm_key_vault.main.network_acls[0].default_action == "Deny" &&
      toset(azurerm_key_vault.main.network_acls[0].ip_rules) == toset(["203.0.113.0/24"]) &&
      azurerm_key_vault.main.purge_protection_enabled == true
    )
    error_message = "Key Vault answers only api_cidrs, and a deleted secret can be recovered"
  }
}

run "the_chart_finds_both_storage_classes" {
  command = apply
  assert {
    condition = (
      kubernetes_storage_class_v1.volumes.storage_provisioner == "disk.csi.azure.com" &&
      kubernetes_storage_class_v1.volumes.parameters.skuName == "Premium_ZRS" &&
      kubernetes_storage_class_v1.shared.storage_provisioner == "file.csi.azure.com" &&
      kubernetes_storage_class_v1.shared.parameters.networkEndpointType == "privateEndpoint" &&
      contains(kubernetes_storage_class_v1.shared.mount_options, "uid=1000")
    )
    error_message = "ospreyflow-volumes on zone-redundant disks, ospreyflow-shared on private Azure Files owned by 1000"
  }
}

run "the_install_answers_name_everything_and_hold_no_secret" {
  command = apply
  assert {
    condition = (
      yamldecode(output.install_answers).mode == "enterprise" &&
      yamldecode(output.install_answers).cloud.provider == "azure" &&
      yamldecode(output.install_answers).cluster.storage_class == "ospreyflow-volumes" &&
      yamldecode(output.install_answers).cluster.shared_storage_class == "ospreyflow-shared" &&
      yamldecode(output.install_answers).external.postgres.sslmode == "require" &&
      yamldecode(output.install_answers).external.valkey.tls == true &&
      yamldecode(output.install_answers).external.media.blob_container == "ospreyflow-media"
    )
    error_message = "the answers carry the cluster's classes and every managed service"
  }
  assert {
    condition     = keys(yamldecode(output.install_answers).external) == ["media", "postgres", "valkey"]
    error_message = "no object store and no search: on Azure both run in the cluster"
  }
  assert {
    condition = alltrue([
      for secret in [
        random_password.database.result,
        azurerm_redis_cache.valkey.primary_access_key,
        azurerm_storage_account.media.primary_access_key,
      ] : !strcontains(output.install_answers, secret)
    ])
    error_message = "no password or key is in the answers"
  }
}
