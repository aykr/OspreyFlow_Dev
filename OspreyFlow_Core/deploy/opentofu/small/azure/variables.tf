# The Small deployment's inputs, the same names on both clouds (ADR-114 decision 10: one shape).
# `ospreyflow install --mode small --cloud azure` fills them from the install answers' `cloud:`.

variable "name" {
  description = "A short prefix for every resource this makes (letters, digits and hyphens)."
  type        = string
  default     = "ospreyflow"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,20}$", var.name))
    error_message = "name is 3 to 21 lower-case letters, digits or hyphens, starting with a letter."
  }
}

variable "region" {
  description = "The Azure region, e.g. uksouth."
  type        = string
}

variable "domain" {
  description = "The name the deployment answers at; the client points it at the output address."
  type        = string
  validation {
    condition     = can(regex("^([a-z0-9]([a-z0-9-]*[a-z0-9])?\\.)+[a-z]{2,}$", var.domain))
    error_message = "domain is a DNS name such as osprey.example.org, with no scheme or path."
  }
}

variable "size" {
  description = "small (32 GB server), medium (64 GB) or large (128 GB); the database follows."
  type        = string
  default     = "small"
  validation {
    condition     = contains(["small", "medium", "large"], var.size)
    error_message = "size is small, medium or large."
  }
}

variable "repository" {
  description = "The address of the OspreyFlow user repository the server clones."
  type        = string
}

variable "backup_days" {
  description = "How many days of backups the cloud keeps, for the server and the database."
  type        = number
  default     = 14
  validation {
    condition     = var.backup_days >= 7 && var.backup_days <= 35
    error_message = "backup_days is between 7 and 35 (Azure Database for PostgreSQL keeps at most 35)."
  }
}

variable "admin_ssh_public_key" {
  description = <<-EOT
    Azure requires a Linux VM to have a sign-in. This key is it; no port is opened for it, so it is
    used only through the Azure serial console or a Bastion the client adds.
  EOT
  type        = string
}

variable "release" {
  description = "The release tag the server installs (empty: the repository's default branch)."
  type        = string
  default     = ""
}

variable "dns_zone" {
  description = "A DNS zone in this account to add the deployment's names to; empty to add them by hand."
  type        = string
  default     = ""
}

variable "admin_email" {
  description = "The first administrator's email (optional)."
  type        = string
  default     = ""
}
