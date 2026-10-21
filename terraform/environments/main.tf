terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.0"
    }
  }
}

provider "kubernetes" {
  config_path    = pathexpand("~/.kube/config")
  config_context = "minikube"
}

module "namespace" {
  source = "../modules/kubernetes-namespace"

  name        = "project15-tf-${terraform.workspace}"
  environment = terraform.workspace
}

output "namespace_name" {
  value = module.namespace.namespace_name
}
