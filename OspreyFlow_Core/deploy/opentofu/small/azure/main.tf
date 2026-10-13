# Small on Azure (ADR-114 decision 8): one VM running the deployment's containers, with Azure's
# managed services underneath — Azure Database for PostgreSQL (flexible server), Blob Storage, Key
# Vault and Azure Backup. The same shape as the AWS module (decision 10).
#
# Choices made here, not in the decision, and recorded in `process/07_BUILD_PLAN.md`'s B6 row:
# - nothing reaches the VM from the internet but 80 and 443; no SSH port is opened (Azure insists on
#   a sign-in for a Linux VM, so a public key is taken, for the serial console or a Bastion);
# - the database is reachable only inside the virtual network (a delegated subnet and private DNS);
# - **Azure has no automatic repair for a single VM** — that is a scale-set feature. Azure's own
#   service healing moves a VM off failed hardware, and Docker restarts the stack; that is the
#   recovery here, and the decision's "VM auto-repair" is put to the owner rather than met by
#   turning one server into a scale set;
# - the database password is generated here and so is in this state file (Azure's flexible server
#   takes a password, not a managed secret), and is copied into Key Vault for the server to read.
#   The state must be kept as a secret; `ospreyflow install` keeps it in the client's own storage.

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

locals {
  vm_size = { small = "Standard_E4s_v5", medium = "Standard_E8s_v5", large = "Standard_E16s_v5" }[var.size]
  db_sku = {
    small  = "B_Standard_B2ms"
    medium = "GP_Standard_D2ds_v5"
    large  = "GP_Standard_D4ds_v5"
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
  address_space       = ["10.41.0.0/16"]
}

resource "azurerm_subnet" "server" {
  name                 = "server"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.41.1.0/24"]
}

resource "azurerm_subnet" "database" {
  name                 = "database"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.41.2.0/24"]
  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_network_security_group" "server" {
  name                = "${var.name}-server"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
}

resource "azurerm_network_security_rule" "web" {
  for_each                    = { "80" = 100, "443" = 110 }
  name                        = "web-${each.key}"
  priority                    = each.value
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = each.key
  source_address_prefix       = "Internet"
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.main.name
  network_security_group_name = azurerm_network_security_group.server.name
}

resource "azurerm_subnet_network_security_group_association" "server" {
  subnet_id                 = azurerm_subnet.server.id
  network_security_group_id = azurerm_network_security_group.server.id
}

resource "azurerm_public_ip" "server" {
  name                = "${var.name}-server"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "server" {
  name                = "${var.name}-server"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.server.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.server.id
  }
}

# --- data: database, object store, secrets ---------------------------------------------------

resource "azurerm_private_dns_zone" "postgres" {
  name                = "${var.name}.private.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = var.name
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.main.id
}

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
  storage_mb                    = 65536
  backup_retention_days         = var.backup_days
  delegated_subnet_id           = azurerm_subnet.database.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  public_network_access_enabled = false
  administrator_login           = "osprey"
  administrator_password        = random_password.database.result
  depends_on                    = [azurerm_private_dns_zone_virtual_network_link.postgres]
  lifecycle {
    # A `tofu destroy` must not take the database with it unasked; remove this line to mean it.
    prevent_destroy = true
    ignore_changes  = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "ospreyflow" {
  name      = "ospreyflow"
  server_id = azurerm_postgresql_flexible_server.main.id
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
  # The Blob media adapter signs with the account's Shared Key (`adapters/media_blob`).
  shared_access_key_enabled = true
  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = var.backup_days
    }
  }
}

resource "azurerm_storage_container" "media" {
  name                  = "ospreyflow-media"
  storage_account_id    = azurerm_storage_account.media.id
  container_access_type = "private"
}

resource "azurerm_key_vault" "main" {
  name                       = "${local.compact}${random_string.suffix.result}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 30
}

# Whoever runs this writes the first secrets; the server reads them.
resource "azurerm_role_assignment" "deployer_writes_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "server_reads_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_virtual_machine.server.identity[0].principal_id
}

resource "azurerm_key_vault_secret" "database_password" {
  name         = "database-password"
  value        = random_password.database.result
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_writes_secrets]
}

resource "azurerm_key_vault_secret" "storage_key" {
  name         = "media-storage-key"
  value        = azurerm_storage_account.media.primary_access_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_writes_secrets]
}

# The first administrator's one-time code (Amendment 10 point 4): made holding "pending"; the
# server's first boot writes the code — the one secret it may write, by a role on this secret alone
# — and the operator's install command reads it once and deletes it.
resource "azurerm_key_vault_secret" "first_admin_code" {
  name         = "first-admin-code"
  value        = "pending"
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_writes_secrets]
  lifecycle {
    ignore_changes = [value]
  }
}

resource "azurerm_role_assignment" "server_writes_first_admin_code" {
  scope                = azurerm_key_vault_secret.first_admin_code.resource_versionless_id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = azurerm_linux_virtual_machine.server.identity[0].principal_id
}

# --- the server ----------------------------------------------------------------------------------

resource "azurerm_linux_virtual_machine" "server" {
  name                  = "${var.name}-server"
  resource_group_name   = azurerm_resource_group.main.name
  location              = azurerm_resource_group.main.location
  size                  = local.vm_size
  admin_username        = "osprey"
  network_interface_ids = [azurerm_network_interface.server.id]
  custom_data = base64encode(templatefile("${path.module}/../cloud-init.yaml.tftpl", {
    provider           = "azure"
    repository         = var.repository
    release            = var.release
    domain             = var.domain
    region             = var.region
    answers            = yamlencode(local.answers)
    database_secret    = ""
    first_admin_secret = ""
    key_vault          = azurerm_key_vault.main.name
  }))
  admin_ssh_key {
    username   = "osprey"
    public_key = var.admin_ssh_public_key
  }
  identity {
    type = "SystemAssigned"
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 200
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

# --- backups -------------------------------------------------------------------------------------

resource "azurerm_recovery_services_vault" "main" {
  name                = var.name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
}

resource "azurerm_backup_policy_vm" "daily" {
  name                = "${var.name}-daily"
  resource_group_name = azurerm_resource_group.main.name
  recovery_vault_name = azurerm_recovery_services_vault.main.name
  backup {
    frequency = "Daily"
    time      = "03:00"
  }
  retention_daily {
    count = var.backup_days
  }
}

resource "azurerm_backup_protected_vm" "server" {
  resource_group_name = azurerm_resource_group.main.name
  recovery_vault_name = azurerm_recovery_services_vault.main.name
  source_vm_id        = azurerm_linux_virtual_machine.server.id
  backup_policy_id    = azurerm_backup_policy_vm.daily.id
}

# --- the install's answers, and the names (Amendment 10 points 1, 2 and 3) ------------------------

locals {
  # What the server's first boot installs from: no secret in it — the passwords are read on the
  # server with its own identity. No `object_store`: on Azure the S3-protocol stores stay on the
  # server (Amendment 10 point 2); media goes to Blob.
  answers = {
    mode = "small"
    cloud = merge(
      { provider = "azure", region = var.region, domain = var.domain },
      var.admin_email == "" ? {} : { admin_email = var.admin_email },
    )
    external = {
      postgres = {
        host     = azurerm_postgresql_flexible_server.main.fqdn
        port     = 5432
        database = "ospreyflow"
        user     = "osprey"
        sslmode  = "require"
      }
      media = {
        blob_account   = azurerm_storage_account.media.name
        blob_container = azurerm_storage_container.media.name
      }
    }
  }
  # Each name the front proxy answers, relative to the zone ("@" for the zone's own apex).
  names = {
    for name in [var.domain, "id.${var.domain}", "bi.${var.domain}"] :
    name => (name == var.dns_zone ? "@" : trimsuffix(name, ".${var.dns_zone}"))
  }
}

data "azurerm_dns_zone" "names" {
  count = var.dns_zone == "" ? 0 : 1
  name  = var.dns_zone
}

resource "azurerm_dns_a_record" "names" {
  for_each            = var.dns_zone == "" ? {} : local.names
  name                = each.value
  zone_name           = data.azurerm_dns_zone.names[0].name
  resource_group_name = data.azurerm_dns_zone.names[0].resource_group_name
  ttl                 = 300
  records             = [azurerm_public_ip.server.ip_address]
}
