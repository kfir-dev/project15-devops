# Checkov exception: PostgreSQL UID

Recorded: 2026-10-19.

Check: CKV_K8S_40.
Scope: the chart's database Deployment only.

PostgreSQL runs with UID/GID 999 and fsGroup 999. The existing persistent
data uses this identity. Changing it solely to satisfy a high-UID check
could prevent PostgreSQL from accessing its existing PVC.

Retained controls include non-root execution, no privilege escalation,
dropped Linux capabilities, RuntimeDefault seccomp, read-only root
filesystem, resource limits and Recreate deployment strategy.

The exception is recorded as a resource annotation, not a global scanner
exclusion. It must remain visible as SKIPPED in scan results.
Reassess when changing the PostgreSQL image, volume ownership or runtime
security policy. Moving to a different UID requires an isolated restore
test and a planned data-permission migration.

No exception is added for image digests or image pull policies.
