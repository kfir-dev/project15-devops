terraform {
  required_version = ">= 1.16.0, < 2.0.0"

  backend "pg" {
    schema_name = "project15_terraform"
  }
}
