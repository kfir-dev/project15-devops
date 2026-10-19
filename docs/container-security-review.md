# Container security review

## Verified checkpoint: 2026-10-19

Jenkins project15-ci build 3 completed successfully using DevOps commit
36da414 and application commit 6eced3c06c8a6b1c66184d23bd10ab12051e27bc.

Verified stages:
- Full-history GitLeaks scans of both repositories.
- Python lint, tests and coverage.
- SonarQube analysis and Quality Gate.
- Docker image build.
- Trivy vulnerability scan and CRITICAL gate.

Archived reports:
- application/reports/coverage.xml
- application/reports/scan-report.json

## Findings

Scanner: Trivy 0.69.3, pinned by image digest.

The archived scan reported:
- CRITICAL: 0 findings.
- HIGH: 44 findings, all in Debian packages.

The HIGH findings have no FixedVersion recorded in this report.
This does not establish that fixes are unavailable elsewhere.
A successful CRITICAL gate does not mean the image has no vulnerabilities.

## Open follow-up

Review the HIGH findings against Debian security advisories, assess
application exposure, and track applicable package or base-image updates.
Retain the findings in reports and rescan after updates.
This checkpoint does not record risk acceptance or production approval.

## Local SBOM and Grype verification: 2026-10-19

Syft 1.54.1 produced a CycloneDX SBOM with 2,853 components.
The SBOM parsed successfully and contained Flask and Gunicorn.
Jenkins build 4 successfully archived sbom.json alongside the coverage
and Trivy reports.

Grype 0.120.1 scanned the locally generated SBOM and reported:
- CRITICAL: 0
- HIGH: 55
- MEDIUM: 64
- LOW: 12
- NEGLIGIBLE: 47
- UNKNOWN: 0

The local Grype CRITICAL gate passed. Non-critical findings remain open
for review; this does not record risk acceptance.
The new Jenkins Grype stage still requires an integration run.
