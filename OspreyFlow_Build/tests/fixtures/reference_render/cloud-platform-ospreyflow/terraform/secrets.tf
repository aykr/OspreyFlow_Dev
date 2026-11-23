# Our own secrets, read by every workload from one Kubernetes Secret: each password made
# here, and each key a person holds (a model engine's, a connection's) given as a variable.

resource "random_password" "osprey_arcadedb_cluster_token" {
  length  = 32
  special = false
}

resource "random_password" "osprey_arcadedb_password" {
  length  = 32
  special = false
}

resource "random_password" "osprey_clickhouse_password" {
  length  = 32
  special = false
}

resource "random_password" "osprey_litellm_db_password" {
  length  = 32
  special = false
}

resource "random_password" "osprey_litellm_master_secret" {
  length  = 32
  special = false
}

resource "random_password" "osprey_litellm_salt_secret" {
  length  = 32
  special = false
}

resource "random_password" "osprey_oidc_client_secret" {
  length  = 32
  special = false
}

resource "kubernetes_secret" "ospreyflow_secrets" {
  metadata {
    name      = "ospreyflow-secrets"
    namespace = var.namespace
  }

  data = {
    ARCADEDB_ROOT_PASSWORD        = random_password.osprey_arcadedb_password.result
    CLICKHOUSE_PASSWORD           = random_password.osprey_clickhouse_password.result
    OSPREY_ARCADEDB_CLUSTER_TOKEN = random_password.osprey_arcadedb_cluster_token.result
    OSPREY_ARCADEDB_PASSWORD      = random_password.osprey_arcadedb_password.result
    OSPREY_CLICKHOUSE_PASSWORD    = random_password.osprey_clickhouse_password.result
    OSPREY_LITELLM_DB_PASSWORD    = random_password.osprey_litellm_db_password.result
    OSPREY_LITELLM_MASTER_SECRET  = random_password.osprey_litellm_master_secret.result
    OSPREY_LITELLM_SALT_SECRET    = random_password.osprey_litellm_salt_secret.result
    OSPREY_OIDC_CLIENT_SECRET     = random_password.osprey_oidc_client_secret.result
  }
}
