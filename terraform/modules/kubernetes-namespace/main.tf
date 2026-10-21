variable "name" {
  description = "Name of the Kubernetes namespace"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.name

    labels = {
      "app.kubernetes.io/part-of"    = "project15"
      "app.kubernetes.io/managed-by" = "terraform"
      "environment"                  = var.environment
    }
  }
}

output "namespace_name" {
  description = "Created Kubernetes namespace"
  value       = kubernetes_namespace_v1.this.metadata[0].name
}
