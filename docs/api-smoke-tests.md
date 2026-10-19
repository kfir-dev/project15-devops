# API smoke tests

Run with:
```bash
python3 ci/test-api.py "$HOME/project15-security-check-reports"
```

The runner uses digest-pinned Newman on the Minikube Docker network.
Requests reach the live application through Ingress with Host project15.local.

Three read-only requests cover:
- /health/live
- /health/ready, including the database status response
- /api/products, including list and count consistency

The collection contains 15 assertions. Request and script timeouts are
bounded. Failures return a non-zero exit code. The temporary Newman
container is removed, and newman.xml is retained for Jenkins.

## Verified local checkpoint: 2026-10-19

All 3 requests and all 15 assertions passed against Helm revision 13.
The JUnit report contained 15 passing test cases.

The Jenkins stage now follows deployment of the image published by the same
build. See deployment-automation.md for deployment guards and backup behavior.
These smoke tests complement the Python suite and do not cover full
product, cart and order write workflows.

Jenkins build 8 verified the active-deployment smoke stage.
The new deployment and post-deployment test sequence still requires verification.
