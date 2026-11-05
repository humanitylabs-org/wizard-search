"""Strict identity for the reviewed dual Docker-save/OCI, uncompressed-layer archive.

Docker engines may expose either the config digest or the OCI manifest digest as
image Id. Neither is a wildcard: bind both to the tagged, hash-checked graph.
No extraction, Docker calls, or writes occur here. Unsupported layouts fail closed.
"""
import hashlib
import json
import re
import tarfile
from typing import Any

MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
CONFIG = 'application/vnd.oci.image.config.v1+json'
LAYER = 'application/vnd.oci.image.layer.v1.tar'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def blob_path(digest):
    require(isinstance(digest, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', digest),
            'Invalid sha256 descriptor')
    return 'blobs/sha256/' + digest.split(':')[1]


def archive_identity(archive, expected):
    """Validate archive checksum, unique tag, descriptors, config and layer bytes."""
    with archive.open('rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() == expected['image_archive_sha256'],
                'Archive checksum differs')
    with tarfile.open(archive, 'r:') as tar:
        members = tar.getmembers()
        require(len({m.name for m in members}) == len(members), 'Duplicate archive members')
        entries = {m.name: m for m in members}

        def member(name):
            require(name in entries and entries[name].isfile(), 'Missing/non-file archive member: ' + name)
            return entries[name]

        def read_json(name) -> Any:
            require(member(name).size <= 4 * 1024 * 1024, 'Oversized image metadata')
            stream = tar.extractfile(name)
            assert stream is not None  # member() already requires a regular file.
            with stream:
                return json.load(stream)

        def descriptor(desc, media_type, metadata=False) -> Any:
            require(desc.get('mediaType') == media_type, 'Unsupported descriptor media type')
            name = blob_path(desc['digest'])
            entry = member(name)
            require(type(desc.get('size')) is int and desc['size'] == entry.size,
                    'Descriptor size differs')
            stream = tar.extractfile(name)
            assert stream is not None
            with stream:
                digest = hashlib.sha256()
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                require('sha256:' + digest.hexdigest() == desc['digest'],
                        'Descriptor blob hash differs')
            return read_json(name) if metadata else name

        tag = expected['image']
        rows = [r for r in read_json('manifest.json') if tag in r.get('RepoTags', [])]
        require(len(rows) == 1, 'Expected one exact Docker-save tag')
        row = rows[0]
        index = read_json('index.json')
        require(index.get('schemaVersion') == 2, 'Unsupported OCI index')
        # The current Docker-save layout uses containerd's fully qualified name.
        names = {tag}
        if '/' not in tag:
            names.add('docker.io/library/' + tag)
        matches = [d for d in index['manifests']
                   if d.get('annotations', {}).get('io.containerd.image.name') in names
                   or d.get('annotations', {}).get('org.opencontainers.image.ref.name') == tag]
        require(len(matches) == 1, 'Expected one exact tagged OCI descriptor')
        selected = matches[0]
        image = descriptor(selected, MANIFEST, metadata=True)
        require(image.get('schemaVersion') == 2 and image.get('mediaType') == MANIFEST,
                'Invalid OCI image manifest')
        require(image['config']['digest'] == expected['image_id'], 'Tested config identity differs')
        require(row['Config'] == blob_path(expected['image_id']), 'Docker-save config differs')
        config = descriptor(image['config'], CONFIG, metadata=True)
        require(config.get('architecture') == 'amd64' and config.get('os') == 'linux',
                'Expected linux/amd64 image')
        platform = selected.get('platform')
        if platform is not None:
            require(platform.get('architecture') == 'amd64' and platform.get('os') == 'linux',
                    'OCI descriptor platform differs')
        require(config['config'].get('Labels', {}).get('org.opencontainers.image.revision') ==
                expected.get('image_source_sha', expected['source_sha']), 'Archive revision differs')
        layers = image['layers']
        require(row['Layers'] == [blob_path(d['digest']) for d in layers],
                'Docker-save layer order differs')
        # Uncompressed OCI layers: their blob digests are also their rootfs diff IDs.
        require(config['rootfs'] == {'type': 'layers', 'diff_ids': [d['digest'] for d in layers]},
                'Config rootfs chain differs')
        for layer in layers:
            descriptor(layer, LAYER)
        return {'archive_sha256': expected['image_archive_sha256'], 'image': tag,
                'config_id': expected['image_id'], 'manifest_id': selected['digest'],
                'config': config}


def loaded_identity(graph, inspected):
    """Validate the loaded image, returning only the durable identity receipt."""
    require(inspected.get('Id') in (graph['config_id'], graph['manifest_id']),
            'Loaded image ID is not the pinned config or manifest')
    config = graph['config']
    require(inspected.get('Architecture') == config['architecture'] and inspected.get('Os') == config['os'],
            'Loaded platform differs')
    require(inspected.get('RootFS') == {'Type': config['rootfs']['type'],
                                      'Layers': config['rootfs']['diff_ids']}, 'Loaded rootfs chain differs')
    actual = inspected.get('Config') or {}
    require(all(key in actual and actual[key] == value for key, value in config['config'].items()),
            'Loaded image config differs')
    return {key: graph[key] for key in ('archive_sha256', 'image', 'config_id', 'manifest_id')} | {
        'effective_image_id': inspected['Id']}
