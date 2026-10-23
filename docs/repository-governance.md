# Public repositories and protected main branches

## Visibility and publication review

The application and DevOps repositories are public:

- https://github.com/kfir-dev/project15-app
- https://github.com/kfir-dev/project15-devops

Before changing visibility, both Git histories passed GitLeaks. A separate
review covered 69 GitHub Actions runs and ten unexpired application artifacts;
199 extracted text files were inspected without incomplete or binary items.
Twenty generic-key findings were individually confirmed as the official
public Python GPG fingerprint in container metadata. No global scanner
suppression was added. The example database password was replaced with an
explicit placeholder after confirming it did not match the active baseline
or GitOps database credentials.

Protected audit records remain outside Git. These checks reduce accidental
exposure risk; they are not a guarantee that every possible secret pattern
or future change is covered. Runtime credentials and database data remain
outside the public repositories.

## Main-branch rules

Rules were configured and read back for both repositories on 2026-10-23:

- Pull requests are required, including for administrators.
- Required checks must pass and the branch must be up to date.
- Review conversations must be resolved.
- Force pushes and branch deletion are disabled.
- Required approving reviews are not configured for this solo project.

| Repository | Required checks |
| --- | --- |
| project15-app | Scan Git history; Trivy and SBOM; Lint and test |
| project15-devops | Scan Git history |

PR #1 and PR #2 subsequently completed their required secret-history checks
and were merged through the pull-request flow. The main branches should
continue to receive changes through PRs rather than direct pushes.

Required GitHub checks and Jenkins verification have distinct scopes.
The DevOps PR check does not replace the full Jenkins delivery pipeline.
Build #16 is the recorded successful delivery checkpoint for these fixes.
