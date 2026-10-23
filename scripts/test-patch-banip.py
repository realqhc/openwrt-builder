#!/usr/bin/env python3
"""Regression checks for the build-time banIP extraction repair."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('patch_banip', Path(__file__).with_name('patch-banip.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ORIGINAL = (Path(__file__).parent / 'fixtures/banip-log-parser.awk').read_text()

# Synthetic inputs use documentation addresses and link-local zone examples.
CASES = [
    ('[2001:db8::123]:443: TLS error', '2001:db8::123', '2001:db8::123'),
    ('[2001:db8::]:443: TLS error', '2001:db8::', '2001:db8::'),
    ('[2001:db8::123]:443 TLS error', '2001:db8::123', '2001:db8::123'),
    ('[2001:db8::123]:443:error', '2001:db8::123', '2001:db8::123'),
    ('[2001:db8::123]:443abc', '2001:db8::123', '2001:db8::123'),
    ('[2001:db8:1:2:3:4:5:6]:65535: error', '2001:db8:1:2:3:4:5:6', '2001:db8:1:2:3:4:5:6'),
    ('peer 192.0.2.15:443 error', '192.0.2.15', '192.0.2.15'),
    ('peer <2001:db8::123> error', '2001:db8::123', '2001:db8::123'),
    ('peer [2001:db8::123] error', '2001:db8::123', '2001:db8::123'),
    ('peer [2001:db8::123]: error', '2001:db8::123', '2001:db8::123'),
    ('peer [2001:db8::123]dead', '2001:db8::123', '2001:db8::123'),
    ('peer <2001:db8::123>dead', '2001:db8::123', '2001:db8::123'),
    ('peer [2001:db8::]: error', '2001:db8::', '2001:db8::'),
    ('peer [::]:443: error', '::', '::'),
    ('peer 2001:db8:: error', '2001:db8::', '2001:db8::'),
    ('peer 2001:db8:1:2:3:4:5:6 error', '2001:db8:1:2:3:4:5:6', '2001:db8:1:2:3:4:5:6'),
    ('peer [fe80::123%eth0]:443: error', 'fe80::123', 'fe80::123'),
    ('peer [fe80::123%eth0.7-test_1] error', 'fe80::123', 'fe80::123'),
    ('from [2001:db8::1]:443: to [2001:db8::2]:8443: error', '2001:db8::1', '2001:db8::2'),
    ('from [2001:db8::]:443 to [2001:db8:1::]:8443 error', '2001:db8::', '2001:db8:1::'),
    ('from 192.0.2.1:443 to [2001:db8::2]:8443: error', '192.0.2.1', '2001:db8::2'),
    ('from [2001:db8::1]:443 to 192.0.2.2:8443: error', '2001:db8::1', '192.0.2.2'),
    ('from 192.0.2.1:443 to 192.0.2.2:8443: error', '192.0.2.1', '192.0.2.2'),
    ('from 2001:db8::1 to [2001:db8::2]:8443 error', '2001:db8::1', '2001:db8::2'),
    ('from [2001:db8::1]:443 to 2001:db8::2 error', '2001:db8::1', '2001:db8::2'),
    ('from <2001:db8::1> to [2001:db8::2]:8443:error', '2001:db8::1', '2001:db8::2'),
    ('peer [192.0.2.15]:443: error', '192.0.2.15', '192.0.2.15'),
    ('peer [192.0.2.15]:443:error', '192.0.2.15', '192.0.2.15'),
    ('from [192.0.2.1]:443: to [2001:db8::2]:8443: error', '192.0.2.1', '2001:db8::2'),
    ('from [2001:db8::1]:443: to [192.0.2.2]:8443: error', '2001:db8::1', '192.0.2.2'),
    ('peer [192.0.2.15]dead', '192.0.2.15', '192.0.2.15'),
    ('peer disconnected without an address', None, None),
]


class BanIPFixTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tree = Path(temporary.name)
        package = self.tree / 'feeds/packages/net/banip'
        (package / 'files').mkdir(parents=True)
        self.source = package / 'files/banip-functions.sh'
        self.recipe = package / 'Makefile'
        self.source.write_text(ORIGINAL)
        self.recipe.write_text('PKG_RELEASE:=2\n')

    def assert_rejected_without_changes(self):
        before = self.source.read_bytes(), self.recipe.read_bytes()
        with self.assertRaises(SystemExit):
            module.patch(self.tree)
        self.assertEqual((self.source.read_bytes(), self.recipe.read_bytes()), before)

    def test_patch_and_repeat(self):
        module.patch(self.tree)
        first = self.source.read_text()
        module.patch(self.tree)
        self.assertEqual(self.source.read_text(), first)
        self.assertEqual(self.recipe.read_text(), 'PKG_RELEASE:=2.2\n')
        self.assertIn(module.NEW_PICK, first)
        self.assertNotIn(module.OLD_NORMALIZE, first)

    def test_migrate_previous_patch(self):
        module.patch(self.tree)
        expected = self.source.read_text()
        self.source.write_text(ORIGINAL.replace(module.OLD_NORMALIZE, module.LEGACY_NORMALIZE))
        self.recipe.write_text('PKG_RELEASE:=2.1\n')
        module.patch(self.tree)
        module.patch(self.tree)
        self.assertEqual(self.source.read_text(), expected)
        self.assertEqual(self.recipe.read_text(), 'PKG_RELEASE:=2.1.2\n')

    def test_already_fixed_upstream_keeps_release(self):
        module.patch(self.tree)
        self.recipe.write_text('PKG_RELEASE:=3\n')
        module.patch(self.tree)
        self.assertEqual(self.recipe.read_text(), 'PKG_RELEASE:=3\n')

    def test_unknown_parser_stops(self):
        self.source.write_text(ORIGINAL.replace('function pick_ip(', 'function changed_pick_ip('))
        self.assert_rejected_without_changes()

    def test_unknown_release_stops(self):
        self.recipe.write_text('PKG_RELEASE:=$(AUTORELEASE)\n')
        self.assert_rejected_without_changes()

    def test_partial_patch_stops(self):
        self.source.write_text(ORIGINAL.replace(module.OLD_BEGIN, module.NEW_BEGIN))
        self.assert_rejected_without_changes()

    def test_duplicate_normalizer_stops(self):
        self.source.write_text(ORIGINAL + module.OLD_NORMALIZE + module.LEGACY_NORMALIZE)
        self.assert_rejected_without_changes()

    def test_mixed_old_and_new_stops(self):
        module.patch(self.tree)
        self.source.write_text(self.source.read_text() + module.LEGACY_NORMALIZE)
        self.assert_rejected_without_changes()

    def test_actual_parser_behavior(self):
        module.patch(self.tree)
        program = self.source.read_text()
        def run(text, mapping='', threshold=1):
            return subprocess.run(
                ['gawk', '-v', f'threshold={threshold}', '-v', 'limit=5000', program],
                input=text, text=True, capture_output=True, check=True,
                env=dict(os.environ, ban_logterm_map=mapping)).stdout
        def block(ip):
            return '' if ip is None else 'BLOCK ' + ip + (' .v4\n' if '.' in ip else ' .v6\n')
        for record, first, last in CASES:
            for mode, expected in [('first', first), ('last', last)]:
                with self.subTest(record=record, mode=mode):
                    self.assertEqual(run(record + '\n', mode + '\x1f.*'), block(expected))
        record = 'from [2001:db8::1]:443: to [2001:db8::2]:8443: error\n'
        self.assertEqual(run(record), block('2001:db8::2'))
        mapping = 'first\x1f^FIRST\x1elast\x1f^LAST'
        self.assertEqual(run('FIRST ' + record + 'LAST ' + record, mapping),
                         block('2001:db8::1') + block('2001:db8::2'))
        self.assertEqual(run(record * 2, 'first\x1f.*', 2), block('2001:db8::1'))
        self.assertEqual(run(record, 'first\x1f.*', 2), '')


if __name__ == '__main__':
    unittest.main()
