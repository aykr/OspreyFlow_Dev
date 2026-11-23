# Decision 4: the platform's OpenSearch 2.x, encrypted, HTTPS only, inside the VPC,
# reached on 443 from the namespace's networks alone and answering the namespace
# role's SigV4-signed requests alone; no fine-grained access control, so no user or
# password. Not backed up: the index is rebuilt from the graph (ADR-150), and goes
# with the domain.

resource "aws_security_group" "search" {
  name   = "${var.namespace}-search"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["172.20.0.0/16"]
  }
}

data "aws_iam_policy_document" "search" {
  statement {
    actions = ["es:ESHttp*"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.service.arn]
    }

    resources = ["${aws_opensearch_domain.search.arn}/*"]
  }
}

resource "aws_opensearch_domain_policy" "search" {
  domain_name     = aws_opensearch_domain.search.domain_name
  access_policies = data.aws_iam_policy_document.search.json
}

resource "aws_opensearch_domain" "search" {
  domain_name    = "${var.namespace}-search"
  engine_version = "OpenSearch_2.17"

  cluster_config {
    instance_type          = "t3.medium.search"
    instance_count         = 2
    zone_awareness_enabled = true

    zone_awareness_config {
      availability_zone_count = 2
    }
  }

  ebs_options {
    ebs_enabled = true
    volume_size = 50
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  vpc_options {
    subnet_ids         = [var.subnet_ids[0], var.subnet_ids[1]]
    security_group_ids = [aws_security_group.search.id]
  }
}

resource "kubernetes_secret" "opensearch_output" {
  metadata {
    name      = "opensearch-output"
    namespace = var.namespace
  }

  data = {
    proxy_url = "https://${aws_opensearch_domain.search.endpoint}"
  }
}
