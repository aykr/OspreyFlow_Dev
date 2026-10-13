# The Small deployment's promises on Azure (ADR-114 decisions 6, 8 and 10), planned against mock
# providers so they run in CI with no credentials. The same promises as the AWS module's tests.

mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id = "00000000-0000-0000-0000-000000000001"
      object_id = "00000000-0000-0000-0000-000000000002"
    }
  }
  mock_resource "azurerm_resource_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test"
    }
  }
  mock_resource "azurerm_virtual_network" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Network/virtualNetworks/osprey-test"
    }
  }
  mock_resource "azurerm_subnet" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Network/virtualNetworks/osprey-test/subnets/server"
    }
  }
  mock_resource "azurerm_network_security_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Network/networkSecurityGroups/osprey-test-server"
    }
  }
  mock_resource "azurerm_public_ip" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Network/publicIPAddresses/osprey-test-server"
    }
  }
  mock_resource "azurerm_network_interface" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Network/networkInterfaces/osprey-test-server"
    }
  }
  mock_resource "azurerm_private_dns_zone" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Network/privateDnsZones/osprey-test.private.postgres.database.azure.com"
    }
  }
  mock_resource "azurerm_postgresql_flexible_server" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.DBforPostgreSQL/flexibleServers/osprey-test-x"
    }
  }
  mock_resource "azurerm_storage_account" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Storage/storageAccounts/ospreytestx"
    }
  }
  mock_resource "azurerm_key_vault" {
    defaults = {
      id        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.KeyVault/vaults/ospreytestx"
      vault_uri = "https://ospreytestx.vault.azure.net/"
    }
  }
  mock_resource "azurerm_linux_virtual_machine" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.Compute/virtualMachines/osprey-test-server"
    }
  }
  mock_resource "azurerm_recovery_services_vault" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.RecoveryServices/vaults/osprey-test"
    }
  }
  mock_resource "azurerm_backup_policy_vm" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/osprey-test/providers/Microsoft.RecoveryServices/vaults/osprey-test/backupPolicies/osprey-test-daily"
    }
  }
}
mock_provider "random" {}

variables {
  name                 = "osprey-test"
  region               = "uksouth"
  domain               = "osprey.example.org"
  repository           = "https://example.org/ospreyflow.git"
  admin_ssh_public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINpvmwNByK0aGhbg3Zu/pV3MX4b5P2DW9PBAGNkDhq1P osprey-test" # a throwaway key; its private half was deleted
}

run "only_the_web_ports_are_open_to_the_world" {
  command = plan
  assert {
    condition = alltrue([
      for rule in azurerm_network_security_rule.web : contains(["80", "443"], rule.destination_port_range)
    ])
    error_message = "the server must take nothing from the internet but HTTP and HTTPS"
  }
  assert {
    condition     = length(azurerm_network_security_rule.web) == 2
    error_message = "exactly two inbound rules: 80 for the certificate challenge, 443 for use"
  }
}

run "the_database_is_private_backed_up_and_guarded" {
  command = plan
  assert {
    condition     = azurerm_postgresql_flexible_server.main.public_network_access_enabled == false
    error_message = "the database must not be reachable from the internet"
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.main.backup_retention_days >= 7
    error_message = "the cloud keeps at least a week of database backups"
  }
}

run "the_object_store_is_private_and_encrypted_in_transit" {
  command = plan
  assert {
    condition     = azurerm_storage_account.media.allow_nested_items_to_be_public == false
    error_message = "no container in the media account may be made public"
  }
  assert {
    condition     = azurerm_storage_account.media.min_tls_version == "TLS1_2"
    error_message = "the media account refuses old TLS"
  }
  assert {
    condition     = azurerm_storage_container.media.container_access_type == "private"
    error_message = "the media container is private"
  }
}

run "secrets_are_kept_in_a_vault_that_cannot_be_purged_early" {
  command = plan
  assert {
    condition     = azurerm_key_vault.main.purge_protection_enabled == true
    error_message = "a deleted vault must be recoverable"
  }
}

run "the_server_is_backed_up" {
  command = plan
  assert {
    condition     = azurerm_backup_policy_vm.daily.retention_daily[0].count >= 7
    error_message = "the server's own backups are kept at least a week"
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
