# Local Terraform environments

## Implemented scope

Terraform 1.16.6 manages Kubernetes namespaces in the existing Minikube
cluster through a reusable module at terraform/modules/kubernetes-namespace.

Module inputs are name and environment. The module creates one labeled
namespace and exports namespace_name. The root configuration derives its
namespace name from terraform.workspace and exports the module output.

The Kubernetes provider targets the minikube context. Its version constraint
and committed dependency lock file are retained in terraform/environments.

## Workspaces

The verified workspaces and namespaces are:

| Workspace | Namespace |
| --- | --- |
| dev | project15-tf-dev |
| staging | project15-tf-staging |
| prod | project15-tf-prod |

These are namespace environments. They do not represent three separate
clusters or three deployed application stacks.

## PostgreSQL state backend

The pg backend uses the project15_terraform schema in the terraform_state
database. Its separate Docker service is project15-terraform-state-db,
defined in terraform/backend/compose.yaml.

PostgreSQL is exposed only on 127.0.0.1:5433 and retains its data in the
terraform_state_data named volume. This backend is independent of the
application and SonarQube databases.

The PostgreSQL backend supports state locking through advisory locks.
See https://developer.hashicorp.com/terraform/language/backend/pg.

Credentials must be supplied through protected runtime sources and
environment variables. Never print connection strings, passwords or raw
state contents. Do not commit backend credentials, local initialization
metadata, state files or saved plans.

This is a database-backed local demonstration. It does not provide
off-host disaster recovery or high availability. No backend restore test
is recorded by this verification.

## Verification on 2026-10-22

- Terraform validate returned valid with zero errors and zero warnings.
- Read-only database inspection confirmed separate dev and prod state rows,
  each containing its corresponding namespace resource.
- A saved staging plan contained exactly one namespace creation.
- Applying that plan added one resource, changed zero and destroyed zero.
- Kubernetes reported all three namespaces Active.
- Terraform plan with detailed exit codes returned no changes for dev,
  staging and prod, using the PostgreSQL backend.

The staging operation did not change application Deployments, Secrets,
database specifications or PVCs.

## Operation

Start the existing backend container before Terraform operations and wait
for its health check. Use the initialized configuration directory
terraform/environments.

Provide the existing backend password through PGPASSWORD without displaying
it. Connection settings are PGHOST=127.0.0.1, PGPORT=5433, PGUSER=terraform,
PGDATABASE=terraform_state and PGSSLMODE=disable for this loopback profile.

Select the intended workspace explicitly. Inspect terraform plan before
applying changes and apply the reviewed saved plan.

Saved plans can contain sensitive information. Keep them outside Git with
owner-only permissions and remove them when no longer required.

During shutdown, stop the backend container while retaining its volume.
Never use volume deletion as a shutdown operation.

## Requirement differences

The project specification calls for cluster provisioning and names
S3 plus DynamoDB or Terraform Cloud as remote-state options. This profile
currently manages namespaces in an existing cluster and uses the supported
PostgreSQL backend instead. These differences must be disclosed and must
not be presented as exact completion of those specific requirements.
