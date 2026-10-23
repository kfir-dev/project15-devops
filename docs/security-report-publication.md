# Publishing current security reports

## Problem and scope

Runtime inspection on 2026-10-24 found that the deployed image matched the
retained Jenkins image reference, but both live security-report endpoints
returned content different from that build. The existing pipeline archived
reports without updating the security-reports PVC.

The new pipeline stage runs after guarded deployment and before Newman and
ZAP. It updates only sbom.json and scan-report.json on that existing PVC.
The application continues to mount the volume read-only.

## Guards

- Publication metadata, deployment metadata and the running application
  image must agree on the published digest.
- SBOM generation saves a binding receipt from native Syft metadata and
  the same Docker archive. It verifies the image index/manifest chain reaches
  the scanned runtime configuration and binds the exact CycloneDX file hash.
  Classic Docker configuration IDs are also supported. Trivy ImageID must
  match this runtime configuration, which can differ from the OCI index ID.
- Historical builds without sbom-binding.json are rejected. A new build is
  required; old receipts are not fabricated from unverified report metadata.
- Source files must be bounded JSON objects with the expected formats.
- Both original application PVCs must be Bound.
- The application report mount must remain read-only and use the expected PVC.
- One ready application Pod must run the expected image.
- Application/DB Deployment specifications and PVC identities/specifications
  are compared before and after the update.

## Transfer and recovery

A temporary non-root Pod uses the published application image and mounts
only the report PVC. Its command overrides normal application startup, so
it does not run application startup or migrations. It has no mounted API
token or database credential, a read-only root filesystem, dropped
capabilities, resource limits and a finite active deadline. It is placed
on the application node to share the existing RWO volume.

The Pod uses fsGroup 10001 for the report volume. This can adjust group
permissions on report files; it does not mount the database PVC.

Previous report bytes are backed up outside Git in owner-only storage.
Incoming filenames, JSON and SHA256 hashes are checked before writes.
Files are staged and individually replaced atomically. The two separate
endpoints are not a transactional pair during the short replacement window.

The script compares canonical JSON hashes from the live API with the source
reports. A publication/read-back failure attempts to restore previous
report bytes. A failed restoration requires inspection using the retained
protected backup. The temporary Pod is removed during cleanup.

The Jenkins job already disables concurrent builds. Do not invoke manual
publication concurrently with another build or report publisher.

## Operation

Check-only mode reads build artifacts and cluster metadata without creating
a Pod or modifying reports:

```bash
python3 ci/publish-security-reports.py /path/to/build/reports
```

The Jenkins stage explicitly enables execution:

```bash
python3 ci/publish-security-reports.py ../application/reports --execute
```

Successful execution writes security-reports-publication.json, archived by
Jenkins. It records the deployed image reference, canonical report hashes,
verification flags and protected backup location. Raw report snapshots are
not copied into Git or normal console output.

## Validation

The standard-library test suite covers transfer, malformed JSON, mismatched
hashes, unexpected filenames, snapshot/restore, stale image metadata,
read-only application mounts and the restricted temporary-Pod manifest.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_report_publication.py -v
```

Live repair and a complete Jenkins execution must be verified before
claiming that this change resolved report provenance. Historical build #14
predates this publication stage.
