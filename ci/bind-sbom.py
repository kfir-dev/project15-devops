"""Bind outputs of one Syft invocation to the saved Docker image identity."""
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def verify_archive(archive, root_id, config_id):
    require(all(re.fullmatch(r'sha256:[a-f0-9]{64}', value) for value in (root_id, config_id)), 'Invalid image digest.')
    documents = {}
    docker_manifest = None
    with tarfile.open(archive, 'r|*') as stream:
        for member in stream:
            if not member.isfile() or member.size > 16 * 1024 * 1024:
                continue
            handle = stream.extractfile(member)
            if handle is None:
                continue
            data = handle.read()
            try:
                document = json.loads(data)
            except (ValueError, UnicodeError):
                continue
            if member.name == 'manifest.json':
                require(docker_manifest is None, 'Duplicate Docker archive manifest.')
                docker_manifest = document
            digest = sha(data)
            if member.name.startswith('blobs/sha256/'):
                require(member.name == 'blobs/sha256/' + digest.split(':')[1], 'Archive blob digest differs.')
            documents[digest] = document
    require(config_id in documents, 'Scanned image configuration is absent from archive.')
    config = documents[config_id]
    require(isinstance(config, dict) and config.get('os') == 'linux' and config.get('architecture') == 'amd64', 'Expected Linux amd64 image configuration.')
    if root_id == config_id:
        # Classic Docker uses the config digest as image Id.
        require(isinstance(docker_manifest, list) and len(docker_manifest) == 1, 'Expected one classic Docker image.')
        name = docker_manifest[0].get('Config', '')
        require(name in {config_id.split(':')[1] + '.json', 'blobs/sha256/' + config_id.split(':')[1]}, 'Classic Docker config differs.')
        return
    seen = set()

    def reaches_config(digest):
        if digest in seen:
            return False
        seen.add(digest)
        document = documents.get(digest)
        if not isinstance(document, dict):
            return False
        if document.get('config', {}).get('digest') == config_id:
            return True
        return any(reaches_config(item.get('digest')) for item in document.get('manifests', []) if isinstance(item, dict))

    require(reaches_config(root_id), 'Published image index does not contain the scanned configuration.')


def bind(archive, native_path, sbom_path, root_id):
    native = json.loads(Path(native_path).read_text())
    source = native.get('source', {})
    metadata = source.get('metadata', {})
    config_id = metadata.get('imageID', '')
    require(source.get('type') == 'image', 'Expected Syft image source.')
    verify_archive(archive, root_id, config_id)
    data = Path(sbom_path).read_bytes()
    sbom = json.loads(data)
    component = sbom.get('metadata', {}).get('component', {})
    require(sbom.get('bomFormat') == 'CycloneDX' and component.get('type') == 'container', 'Expected container CycloneDX SBOM.')
    require(component.get('version') == metadata.get('manifestDigest') and re.fullmatch(r'sha256:[a-f0-9]{64}', component.get('version', '')), 'CycloneDX source manifest differs from native Syft output.')
    names = {item.get('name', '').lower() for item in sbom.get('components', [])}
    require({'flask', 'gunicorn'}.issubset(names), 'Expected application dependencies missing.')
    return {'schema_version': 1, 'local_image_id': root_id, 'image_config_id': config_id,
            'syft_manifest_digest': component['version'], 'sbom_sha256': hashlib.sha256(data).hexdigest(),
            'archive_binding_verified': True}


if __name__ == '__main__':
    try:
        archive, native, sbom, image_id, receipt = sys.argv[1:]
        result = bind(archive, native, sbom, image_id)
        Path(receipt).write_text(json.dumps(result, indent=2) + '\n')
        print('PASS: SBOM bound to the saved image index and runtime configuration.')
    except Exception as exc:
        raise SystemExit('STOP: ' + str(exc))
