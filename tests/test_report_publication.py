import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ci/publish-security-reports.py"
if not SCRIPT.is_file():
    SCRIPT = Path(__file__).with_name("publish-security-reports.py")
SPEC = importlib.util.spec_from_file_location("report_publisher", SCRIPT)
PUBLISHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLISHER)
REFERENCE = "ghcr.io/kfir-dev/project15-app@sha256:" + "a" * 64
IMAGE_ID = "sha256:" + "b" * 64

BIND_SCRIPT = SCRIPT.with_name("bind-sbom.py")
BIND_SPEC = importlib.util.spec_from_file_location("sbom_binding", BIND_SCRIPT)
BINDER = importlib.util.module_from_spec(BIND_SPEC)
BIND_SPEC.loader.exec_module(BINDER)


def record(data):
    return {"data": base64.b64encode(data).decode(), "sha256": hashlib.sha256(data).hexdigest()}


class ReportTransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.old = {name: json.dumps({"previous": name}).encode() for name in PUBLISHER.FILES}
        for name, content in self.old.items():
            (self.root / name).write_bytes(content)

    def transfer(self, packet):
        return subprocess.run(
            [sys.executable, "-c", PUBLISHER.RECEIVER, str(self.root)],
            input=json.dumps(packet), capture_output=True, text=True, timeout=15,
        )

    def assert_unchanged(self):
        for name, content in self.old.items():
            self.assertEqual((self.root / name).read_bytes(), content)

    def payload(self):
        return {name: record(json.dumps({"current": name}).encode()) for name in PUBLISHER.FILES}

    def test_publish_updates_both_files_without_leaving_temporary_files(self):
        files = self.payload()
        result = self.transfer({"operation": "publish", "files": files})
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in PUBLISHER.FILES:
            self.assertEqual((self.root / name).read_bytes(), base64.b64decode(files[name]["data"]))
        self.assertFalse(list(self.root.glob(".project15-report-*")))

    def test_malformed_second_report_rejected_before_either_file_changes(self):
        files = self.payload()
        files["scan-report.json"] = record(b"not valid JSON")
        result = self.transfer({"operation": "publish", "files": files})
        self.assertNotEqual(result.returncode, 0)
        self.assert_unchanged()

    def test_mismatched_hash_rejected_before_writing(self):
        files = self.payload()
        files["sbom.json"]["sha256"] = "0" * 64
        self.assertNotEqual(self.transfer({"operation": "publish", "files": files}).returncode, 0)
        self.assert_unchanged()

    def test_unexpected_filename_rejected(self):
        files = self.payload()
        files["../escape.json"] = record(b"{}")
        self.assertNotEqual(self.transfer({"operation": "publish", "files": files}).returncode, 0)
        self.assert_unchanged()
        self.assertFalse((self.root.parent / "escape.json").exists())

    def test_snapshot_can_restore_previous_contents(self):
        snapshot = self.transfer({"operation": "snapshot"})
        self.assertEqual(snapshot.returncode, 0)
        backup = json.loads(snapshot.stdout)["files"]
        self.assertEqual(self.transfer({"operation": "publish", "files": self.payload()}).returncode, 0)
        restored = self.transfer({"operation": "restore", "files": backup})
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assert_unchanged()

    def test_unknown_operation_rejected(self):
        self.assertNotEqual(self.transfer({"operation": "delete-all"}).returncode, 0)
        self.assert_unchanged()


class ReportBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        documents = {
            "image-publication.json": {"image_reference": REFERENCE, "local_image_id": IMAGE_ID},
            "deployment.json": {"image_reference": REFERENCE},
            "sbom.json": {"bomFormat": "CycloneDX", "metadata": {"component": {"type": "container", "version": "sha256:" + "d" * 64}}},
            "scan-report.json": {"Results": [], "Metadata": {"ImageID": IMAGE_ID}},
        }
        for name, data in documents.items():
            (self.root / name).write_text(json.dumps(data))
        (self.root / "sbom-binding.json").write_text(json.dumps({
            "schema_version": 1, "local_image_id": IMAGE_ID, "image_config_id": IMAGE_ID,
            "syft_manifest_digest": "sha256:" + "d" * 64, "archive_binding_verified": True,
            "sbom_sha256": hashlib.sha256((self.root / "sbom.json").read_bytes()).hexdigest(),
        }))
        (self.root / "image-reference.txt").write_text(REFERENCE)
        self.before = {"application_spec": {"template": {"spec": {
            "containers": [{"name": "app", "image": REFERENCE, "volumeMounts": [{"name": "security-reports", "mountPath": "/app/security-reports", "readOnly": True}]}],
            "volumes": [{"name": "security-reports", "persistentVolumeClaim": {"claimName": "project15-security-reports"}}],
        }}}}
        self.pods = {"items": [{"metadata": {"name": "app-ready", "uid": "test"}, "spec": {"nodeName": "minikube", "containers": [{"name": "app", "image": REFERENCE}]}, "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}}]}

    def prepare(self):
        with patch.object(PUBLISHER, "snapshot", return_value=copy.deepcopy(self.before)), patch.object(PUBLISHER, "kubectl", return_value=self.pods):
            return PUBLISHER.prepare(self.root)

    def test_matching_build_metadata_and_readonly_mount_accepted(self):
        self.assertEqual(self.prepare()[0], REFERENCE)

    def test_report_from_different_image_rejected(self):
        path = self.root / "scan-report.json"
        data = json.loads(path.read_text())
        data["Metadata"]["ImageID"] = "sha256:" + "c" * 64
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, "Trivy report image differs"):
            self.prepare()

    def test_oci_index_can_differ_from_runtime_config(self):
        path = self.root / "image-publication.json"
        publication = json.loads(path.read_text())
        publication["local_image_id"] = "sha256:" + "e" * 64
        path.write_text(json.dumps(publication))
        path = self.root / "sbom-binding.json"
        binding = json.loads(path.read_text())
        binding["local_image_id"] = publication["local_image_id"]
        path.write_text(json.dumps(binding))
        self.assertEqual(self.prepare()[0], REFERENCE)

    def test_modified_sbom_rejected(self):
        path = self.root / "sbom.json"
        document = json.loads(path.read_text())
        document["components"] = [{"name": "unexpected"}]
        path.write_text(json.dumps(document))
        with self.assertRaisesRegex(RuntimeError, "SBOM content differs"):
            self.prepare()

    def test_binding_from_another_index_rejected(self):
        path = self.root / "sbom-binding.json"
        binding = json.loads(path.read_text())
        binding["local_image_id"] = "sha256:" + "e" * 64
        path.write_text(json.dumps(binding))
        with self.assertRaisesRegex(RuntimeError, "archive binding differs"):
            self.prepare()

    def test_sbom_without_image_identity_rejected(self):
        (self.root / "sbom.json").write_text(json.dumps({"bomFormat": "CycloneDX", "metadata": {}}))
        with self.assertRaisesRegex(RuntimeError, "SBOM metadata"):
            self.prepare()

    def test_deployed_digest_mismatch_rejected(self):
        self.before["application_spec"]["template"]["spec"]["containers"][0]["image"] = "unexpected"
        with self.assertRaisesRegex(RuntimeError, "Deployed image differs"):
            self.prepare()

    def test_writable_application_report_mount_rejected(self):
        self.before["application_spec"]["template"]["spec"]["containers"][0]["volumeMounts"][0]["readOnly"] = False
        with self.assertRaisesRegex(RuntimeError, "must remain read-only"):
            self.prepare()

    def test_writer_has_only_report_volume_and_no_api_token(self):
        spec = PUBLISHER.writer_manifest("publisher", "nonce", REFERENCE, "minikube")["spec"]
        self.assertFalse(spec["automountServiceAccountToken"])
        self.assertEqual(spec["volumes"], [{"name": "reports", "persistentVolumeClaim": {"claimName": "project15-security-reports"}}])
        self.assertEqual(spec["containers"][0]["image"], REFERENCE)
        self.assertTrue(spec["containers"][0]["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(spec["securityContext"]["runAsUser"], 10001)

    def test_live_hash_failure_restores_backup_and_removes_writer(self):
        calls, created, deleted = [], {}, []
        backup = {name: record(json.dumps({"previous": name}).encode()) for name in PUBLISHER.FILES}

        def fake_run(args, source=None, timeout=90):
            if "create" in args:
                created.update(json.loads(source))
                return "{}"
            if "get" in args and "pod" in args:
                return json.dumps({"metadata": created["metadata"]})
            if "delete" in args:
                deleted.append(args)
                return ""
            self.fail("Unexpected external command in rollback test")

        def fake_transfer(name, operation, files=None):
            calls.append(operation)
            if operation == "snapshot":
                return {"files": backup}
            if operation == "restore":
                self.assertEqual(files, backup)
            return {}

        ready = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        with patch.object(PUBLISHER, "STATE", self.root), patch.object(PUBLISHER, "run", side_effect=fake_run), patch.object(PUBLISHER, "kubectl", return_value=ready), patch.object(PUBLISHER, "snapshot", return_value=self.before), patch.object(PUBLISHER, "transfer", side_effect=fake_transfer), patch.object(PUBLISHER, "observed_hashes", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "Live report contents differ"):
                PUBLISHER.execute(self.root, REFERENCE, {}, {"expected": "hash"}, self.before, self.pods["items"][0])
        self.assertEqual(calls, ["snapshot", "publish", "restore"])
        self.assertEqual(len(deleted), 1)
        self.assertFalse((self.root / "security-reports-publication.json").exists())
        self.assertEqual(len(list(self.root.glob("before-publication-*.json"))), 1)


class ArchiveBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = json.dumps({"os": "linux", "architecture": "amd64", "config": {}}).encode()
        self.config_id = BINDER.sha(self.config)
        self.manifest = json.dumps({"schemaVersion": 2, "config": {"digest": self.config_id}, "layers": []}).encode()
        self.manifest_id = BINDER.sha(self.manifest)
        self.index = json.dumps({"schemaVersion": 2, "manifests": [{"digest": self.manifest_id}]}).encode()
        self.index_id = BINDER.sha(self.index)
        self.archive = self.root / "image.tar"
        with tarfile.open(self.archive, "w") as stream:
            for data in (self.config, self.manifest, self.index):
                member = tarfile.TarInfo("blobs/sha256/" + BINDER.sha(data).split(":")[1])
                member.size = len(data)
                stream.addfile(member, io.BytesIO(data))
            data = json.dumps([{"Config": "blobs/sha256/" + self.config_id.split(":")[1]}]).encode()
            member = tarfile.TarInfo("manifest.json")
            member.size = len(data)
            stream.addfile(member, io.BytesIO(data))

    def test_index_chain_reaches_config(self):
        BINDER.verify_archive(self.archive, self.index_id, self.config_id)

    def test_classic_config_image_identity_accepted(self):
        BINDER.verify_archive(self.archive, self.config_id, self.config_id)

    def test_unrelated_index_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "does not contain"):
            BINDER.verify_archive(self.archive, "sha256:" + "a" * 64, self.config_id)

    def test_unrelated_scanned_config_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "absent from archive"):
            BINDER.verify_archive(self.archive, self.index_id, "sha256:" + "a" * 64)

    def test_cyclonedx_and_native_manifest_must_match(self):
        native = self.root / "native.json"
        sbom = self.root / "sbom.json"
        native.write_text(json.dumps({"source": {"type": "image", "metadata": {"imageID": self.config_id, "manifestDigest": self.manifest_id}}}))
        document = {"bomFormat": "CycloneDX", "metadata": {"component": {"type": "container", "version": self.manifest_id}}, "components": [{"name": "flask"}, {"name": "gunicorn"}]}
        sbom.write_text(json.dumps(document))
        receipt = BINDER.bind(self.archive, native, sbom, self.index_id)
        self.assertEqual(receipt["image_config_id"], self.config_id)
        document["metadata"]["component"]["version"] = "sha256:" + "a" * 64
        sbom.write_text(json.dumps(document))
        with self.assertRaisesRegex(RuntimeError, "source manifest differs"):
            BINDER.bind(self.archive, native, sbom, self.index_id)


if __name__ == "__main__":
    unittest.main()
