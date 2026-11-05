#!/usr/bin/env python3
"""Small stdlib-only tar fixtures. Never loads Docker or touches live state."""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ops'))
from image_archive_identity import archive_identity, loaded_identity, MANIFEST, CONFIG, LAYER


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


class ArchiveIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def fixture(self, config_change=None, docker_change=None, image_change=None,
                index_change=None, corrupt=None, duplicate=False):
        blobs = {}

        def blob(data, media):
            identity = digest(data)
            blobs['blobs/sha256/' + identity.split(':')[1]] = data
            return {'digest': identity, 'size': len(data), 'mediaType': media}

        layers = [blob(data, LAYER) for data in (b'first layer', b'second layer')]
        config = {'architecture': 'amd64', 'os': 'linux',
                  'rootfs': {'type': 'layers', 'diff_ids': [d['digest'] for d in layers]},
                  'config': {'Labels': {'org.opencontainers.image.revision': 'tested-revision'},
                             'Env': ['SAFE=1'], 'Cmd': ['python3', 'server.py'],
                             'WorkingDir': '/app', 'User': '1000:1000', 'ArgsEscaped': True}}
        if config_change:
            config_change(config)
        cfg = blob(encoded(config), CONFIG)
        image = {'schemaVersion': 2, 'mediaType': MANIFEST, 'config': cfg, 'layers': layers}
        if image_change:
            image_change(image)
        desc = blob(encoded(image), MANIFEST)
        desc['annotations'] = {'io.containerd.image.name': 'docker.io/library/search:tested'}
        index = {'schemaVersion': 2, 'manifests': [desc]}
        if index_change:
            index_change(index)
        docker = [{'Config': 'blobs/sha256/' + cfg['digest'].split(':')[1],
                   'RepoTags': ['search:tested'],
                   'Layers': ['blobs/sha256/' + d['digest'].split(':')[1] for d in layers]}]
        if docker_change:
            docker_change(docker)
        blobs.update({'manifest.json': encoded(docker), 'index.json': encoded(index)})
        if corrupt:
            name = {'config': docker[0]['Config'], 'manifest': 'blobs/sha256/' + desc['digest'].split(':')[1],
                    'layer': docker[0]['Layers'][0]}[corrupt]
            blobs[name] = bytes([blobs[name][0] ^ 1]) + blobs[name][1:]
        archive = self.directory / 'fixture.tar'
        with tarfile.open(archive, 'w') as tar:
            for name, data in list(blobs.items()) + ([('index.json', blobs['index.json'])] if duplicate else []):
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                tar.addfile(entry, io.BytesIO(data))
        expected = {'image': 'search:tested', 'image_id': cfg['digest'], 'source_sha': 'operator-revision',
                    'image_source_sha': 'tested-revision',
                    'image_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
        loaded = {'Id': cfg['digest'], 'Architecture': 'amd64', 'Os': 'linux',
                  'Config': copy.deepcopy(config['config']),
                  'RootFS': {'Type': 'layers', 'Layers': config['rootfs']['diff_ids'][:]}}
        return archive, expected, loaded

    def test_accepts_only_two_valid_id_representations(self):
        archive, expected, loaded = self.fixture()
        graph = archive_identity(archive, expected)
        for identity in (graph['config_id'], graph['manifest_id']):
            loaded['Id'] = identity
            receipt = loaded_identity(graph, loaded)
            self.assertEqual(receipt['effective_image_id'], identity)
            self.assertEqual(receipt['config_id'], expected['image_id'])
        loaded['Id'] = 'sha256:' + 'f' * 64
        with self.assertRaisesRegex(ValueError, 'Loaded image ID'):
            loaded_identity(graph, loaded)

    def test_rejects_outer_checksum_and_tested_config_mismatch(self):
        archive, expected, _ = self.fixture()
        for key in ('image_archive_sha256', 'image_id'):
            changed = dict(expected)
            changed[key] = ('sha256:' if key == 'image_id' else '') + '0' * 64
            with self.subTest(key=key), self.assertRaises(ValueError):
                archive_identity(archive, changed)

    def test_rejects_corrupted_descriptor_bytes_even_with_valid_outer_checksum(self):
        for kind in ('config', 'manifest', 'layer'):
            with self.subTest(kind=kind):
                archive, expected, _ = self.fixture(corrupt=kind)
                with self.assertRaisesRegex(ValueError, 'blob hash'):
                    archive_identity(archive, expected)

    def test_rejects_wrong_or_ambiguous_tag(self):
        changes = [lambda d: d[0].update(RepoTags=['search:wrong']), lambda d: d.append(copy.deepcopy(d[0]))]
        for change in changes:
            with self.subTest(change=change):
                archive, expected, _ = self.fixture(docker_change=change)
                with self.assertRaisesRegex(ValueError, 'Docker-save tag'):
                    archive_identity(archive, expected)

    def test_rejects_wrong_index_tag_digest_size_or_ambiguity(self):
        changes = [lambda i: i['manifests'][0]['annotations'].update({'io.containerd.image.name': 'other:tested'}),
                   lambda i: i['manifests'][0].update(digest='sha256:' + '0' * 64),
                   lambda i: i['manifests'][0].update(size=1),
                   lambda i: i['manifests'].append(copy.deepcopy(i['manifests'][0])),
                   lambda i: i['manifests'][0].update(digest='sha256:../escape'),
                   lambda i: i['manifests'][0].update(platform={'os': 'linux', 'architecture': 'arm64'})]
        for change in changes:
            with self.subTest(change=change):
                archive, expected, _ = self.fixture(index_change=change)
                with self.assertRaises(ValueError):
                    archive_identity(archive, expected)

    def test_rejects_wrong_config_link(self):
        archive, expected, _ = self.fixture(docker_change=lambda d: d[0].update(Config='blobs/sha256/' + '0' * 64))
        with self.assertRaisesRegex(ValueError, 'Docker-save config'):
            archive_identity(archive, expected)

    def test_rejects_wrong_layer_chain_order_and_media(self):
        cases = [{'docker_change': lambda d: d[0]['Layers'].reverse()},
                 {'config_change': lambda c: c['rootfs']['diff_ids'].reverse()},
                 {'image_change': lambda i: i['layers'][0].update(size=1)},
                 {'image_change': lambda i: i['layers'][0].update(mediaType=LAYER + '+gzip')}]
        for case in cases:
            with self.subTest(case=case):
                archive, expected, _ = self.fixture(**case)
                with self.assertRaises(ValueError):
                    archive_identity(archive, expected)

    def test_rejects_wrong_platform_and_revision_in_archive(self):
        changes = [lambda c: c.update(architecture='arm64'), lambda c: c.update(os='windows'),
                   lambda c: c['config']['Labels'].update({'org.opencontainers.image.revision': 'wrong'})]
        for change in changes:
            with self.subTest(change=change):
                archive, expected, _ = self.fixture(config_change=change)
                with self.assertRaises(ValueError):
                    archive_identity(archive, expected)

    def test_rejects_duplicate_members(self):
        archive, expected, _ = self.fixture(duplicate=True)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            archive_identity(archive, expected)

    def test_rejects_loaded_platform_rootfs_and_config_drift(self):
        archive, expected, loaded = self.fixture()
        graph = archive_identity(archive, expected)
        changes = [lambda d: d.update(Architecture='arm64'), lambda d: d.update(Os='windows'),
                   lambda d: d['RootFS']['Layers'].reverse(), lambda d: d['Config'].update(Env=['SAFE=0']),
                   lambda d: d['Config']['Labels'].update({'org.opencontainers.image.revision': 'wrong'}),
                   lambda d: d['Config'].pop('Cmd'), lambda d: d['Config'].update(User='root')]
        for change in changes:
            with self.subTest(change=change):
                bad = copy.deepcopy(loaded)
                change(bad)
                with self.assertRaises(ValueError):
                    loaded_identity(graph, bad)

    def test_actual_retirement_guard_accepts_effective_id_and_rejects_stale_receipt(self):
        archive, manifest, loaded = self.fixture()
        manifest['image_archive'] = archive.name
        graph = archive_identity(archive, manifest)
        loaded['Id'] = graph['manifest_id']
        receipt = {'sha': manifest['source_sha'], 'image_identity': loaded_identity(graph, loaded)}
        (self.directory / 'artifact-manifest.json').write_text(json.dumps(manifest))
        (self.directory / 'parent-cutover.json').write_text(json.dumps({'verified': True, 'sha': manifest['source_sha']}))
        source = (ROOT / 'ops/parent-release.py').read_text().split("elif a.action=='retire-legacy':\n")[1]
        block = source.split(" run(['systemctl'")[0]
        code = compile(ast.parse('if True:\n' + block), '<actual retirement guard>', 'exec')
        calls = []

        def call(argv):
            calls.append(argv)
            return json.dumps([loaded] if argv[1:3] == ['image', 'inspect'] else [{'Image': loaded['Id']}])

        values = {'release': self.directory, 'json': json, 'archive_identity': archive_identity,
                  'loaded_identity': loaded_identity, 'call': call, 'container': 'synthetic-search'}
        path = self.directory / 'parent-package-verification.json'
        path.write_text(json.dumps(receipt))
        exec(code, dict(values))
        self.assertEqual(calls[-1], ['docker', 'image', 'inspect', graph['manifest_id']])
        for bad in [dict(receipt, sha='stale'), dict(receipt, image_identity={})]:
            path.write_text(json.dumps(bad))
            with self.assertRaises(AssertionError):
                exec(code, dict(values))

    def test_parent_validates_archive_before_snapshot_and_loaded_image_before_token(self):
        source = (ROOT / 'ops/parent-release.py').read_text()
        self.assertLess(source.index('graph=archive_identity(archive,manifest)'), source.index(' backup.mkdir('))
        self.assertLess(source.index('identity=loaded_identity(graph,img)'), source.index(' token=secrets.'))
        self.assertIn("'image_identity':identity", source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
