# Dockerfile lint gate

The Jenkins pipeline runs ci/lint-dockerfile.py before the existing Python
lint stage. It checks the application Dockerfile using Hadolint v2.15.1,
pinned by digest through HADOLINT_IMAGE in ci/images.env.

The container runs as the invoking user, without network access, with a
read-only root filesystem, dropped capabilities and bounded CPU, memory
and execution time. It receives the Dockerfile through standard input.

Warning and error findings fail the gate. Inline ignore pragmas are
disabled. Missing or malformed JSON reports and nonzero scanner exits
also fail the wrapper.

The wrapper removes its previous hadolint.json before each invocation.
Valid reports are retained even when findings fail the gate. Jenkins
includes application/reports/hadolint.json in artifact archiving.

## Local verification on 2026-10-22

Hadolint initially reported DL3008 because liblzma5 had no explicit package
version in the apt installation instruction.

The Debian trixie security repository offered 5.8.1-1+deb13u2. The
application Dockerfile now pins that version while retaining the explicit
package upgrade and apt-list cleanup.

The updated Dockerfile passed Hadolint with zero findings and exit code
zero. The wrapper generated a valid JSON report.

A temporary Dockerfile containing an untagged Python base image produced
DL3006, a failing gate and a retained JSON report. The fixture was removed.

## Remaining verification and maintenance

The updated image build and Jenkins stage still require verification by
a complete pipeline run. Local lint success does not prove that the image
build or deployment succeeds.

Review the package pin when security updates are released. Debian can
replace older package versions in its repositories, so future builds may
require an explicit reviewed pin update.
