# Enterprise's inputs, the same names on both clouds and the same as Small's where they mean the same
# (ADR-114 decision 10: one shape). The cluster install reads this module's `install_answers`.

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
  description = "The name the deployment answers at; the client points it at the load balancer."
  type        = string
  validation {
    condition     = can(regex("^([a-z0-9]([a-z0-9-]*[a-z0-9])?\\.)+[a-z]{2,}$", var.domain))
    error_message = "domain is a DNS name such as osprey.example.org, with no scheme or path."
  }
}

variable "size" {
  description = "small (3 nodes of 32 GB), medium (4 of 64 GB) or large (6 of 128 GB); the stores follow."
  type        = string
  default     = "small"
  validation {
    condition     = contains(["small", "medium", "large"], var.size)
    error_message = "size is small, medium or large."
  }
}

variable "kubernetes_version" {
  description = "The AKS Kubernetes version."
  type        = string
  default     = "1.34"
}

variable "api_cidrs" {
  description = "The addresses allowed to reach the cluster's API (the operator's network); never the whole internet."
  type        = list(string)
  validation {
    condition     = length(var.api_cidrs) > 0 && !contains(var.api_cidrs, "0.0.0.0/0")
    error_message = "api_cidrs names the operator's own addresses; 0.0.0.0/0 is refused."
  }
}

variable "backup_days" {
  description = "How many days of backups the cloud keeps for the database."
  type        = number
  default     = 14
  validation {
    condition     = var.backup_days >= 7 && var.backup_days <= 35
    error_message = "backup_days is between 7 and 35 (Azure Database for PostgreSQL keeps at most 35)."
  }
}

variable "namespace" {
  description = "The Kubernetes namespace the deployment is installed in."
  type        = string
  default     = "ospreyflow"
}

variable "admin_email" {
  description = "The first administrator's email (optional)."
  type        = string
  default     = ""
}
