# Scoped passive API security scan

## Scope

The Jenkins pipeline runs ci/scan-api.py after deployment and Newman tests.
The scanner uses the digest-pinned ZAP image from ci/images.env and the
versioned OpenAPI specification at ci/zap/api-readonly.openapi.json.

The defined scope is three GET operations through the project15.local Ingress:

- /health/live
- /health/ready
- /api/products

This is a limited passive baseline. It does not establish coverage of the
whole application, authenticated operations, write operations or active
attack testing. Health and listing requests can still generate operational
logs and metrics.

## Execution and validation

The scanner runs on the Minikube Docker network with an explicit host mapping.
Endpoint preflight uses that same network because direct WSL access to the
Minikube address timed out while container-network requests succeeded.

The container runs without root privileges, drops Linux capabilities and
uses bounded CPU, memory and execution time. No scanner port is published
on the host. Runtime add-on updates are disabled.

The coverage hook records operation and status metadata without response
bodies. Validation requires all three scoped GET operations to return HTTP
200, no observed write methods, no unexpected operations, no active scans
and an empty passive-scan queue.

ZAP virtual parent records are distinguished narrowly using their temporary
history type, parent path, GET method, status zero, empty response body and
absence of a query. Real out-of-scope requests are rejected.

## Security gate and reports

The gate rejects any HIGH finding. MEDIUM, LOW and INFORMATIONAL findings
remain visible in the summary and require review.

A native ZAP warning exit code does not itself establish success. The
wrapper accepts only native exit codes zero or two and additionally requires
valid reports, verified coverage and a passing HIGH gate. Missing sites,
unexpected report targets and unknown severity classifications fail validation.

The existing always-run Jenkins artifact step includes:

- zap-report.json
- zap-report.html
- zap-coverage.json
- zap-summary.json

Raw scanner logs remain in protected storage outside Git. Reports can contain
response-derived details; do not commit or paste their raw contents.

## Verified evidence

A local scan before the response-header fix observed all three scoped GET
operations with HTTP 200, completed passive scanning and reported no active
scans. It reported HIGH 0, MEDIUM 0, LOW 1 and INFORMATIONAL 0.

The LOW finding was rule 10021, X-Content-Type-Options Header Missing,
with three instances.

Application commit a94d286 adds X-Content-Type-Options: nosniff.
All 44 application tests and flake8 passed, including four header cases
covering the scoped endpoints and an HTTP 404 response.

Boundary tests rejected a real out-of-scope request and a write method.
Synthetic report tests accepted a clean report and rejected a HIGH finding,
an unknown severity, an unexpected target and missing sites. The HIGH case
also produced failure metadata before rejecting the report.

## Jenkins verification

Jenkins build #10 succeeded using DevOps commit 51fc58a and application
commit a94d286. All four ZAP reports were archived with the build.

The archived summary reported a passing gate and verified coverage:
HIGH 0, MEDIUM 0, LOW 0 and INFORMATIONAL 0.

Coverage metadata reported zero active scans, zero pending passive records,
zero unsafe methods and zero unexpected paths. Rule 10021 was absent,
confirming that the missing nosniff finding was resolved for the three
scoped GET operations in the deployed application.

These results apply to the defined passive scope and do not establish
whole-application or active security-test coverage.
