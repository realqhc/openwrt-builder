#!/usr/bin/env python3
"""Synthetic regression checks for the build-time banIP repair."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('patch_banip', Path(__file__).with_name('patch-banip.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BanIPFixTests(unittest.TestCase):
    def test_patch_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            package = tree / 'feeds/packages/net/banip'
            (package / 'files').mkdir(parents=True)
            source = package / 'files/banip-functions.sh'
            source.write_text(module.OLD + '\n')
            recipe = package / 'Makefile'
            recipe.write_text('PKG_RELEASE:=2\n')
            module.patch(tree)
            module.patch(tree)
            self.assertEqual(source.read_text(), module.NEW + '\n')
            self.assertEqual(recipe.read_text(), 'PKG_RELEASE:=2.1\n')

    def test_unknown_parser_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            source = tree / 'feeds/packages/net/banip/files/banip-functions.sh'
            source.parent.mkdir(parents=True)
            source.write_text('unexpected parser\n')
            with self.assertRaises(SystemExit):
                module.patch(tree)
            self.assertEqual(source.read_text(), 'unexpected parser\n')

    def test_address_boundaries(self):
        # Exercise the repaired normalization with the same IP matching regex
        # used by banIP, including compressed IPv6 ending in ::.
        program = r'''
        {
            sub(/\]:[0-9]+:?/, "] ", $0)
            gsub(/[<>[\]]/, "", $0)
            if (match($0, /([A-Fa-f0-9]{0,4}:){2,7}[A-Fa-f0-9]{0,4}/, m)) print m[0]
        }
        '''
        program = program.replace(r'sub(/\]:[0-9]+:?/, "] ", $0)', module.NEW)
        records = '[2001:db8::123]:443: TLS error\n[2001:db8::]:443: TLS error\n[2001:db8::123]:443 TLS error\n'
        result = subprocess.run(['gawk', program], input=records, text=True,
                                capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines(), ['2001:db8::123', '2001:db8::', '2001:db8::123'])


if __name__ == '__main__':
    unittest.main()
