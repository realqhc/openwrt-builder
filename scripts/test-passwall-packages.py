#!/usr/bin/env python3
"""Regression checks for feed collisions and release version verification."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('selection', Path(__file__).with_name('passwall-packages.py'))
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)


class PackageSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name)
        for recipe in selection.RECIPES:
            path = self.tree / 'feeds' / selection.FEED / recipe
            path.mkdir(parents=True)
            (path / 'Makefile').write_text('')
        self.links = self.tree / 'package/feeds'
        (self.links / 'packages').mkdir(parents=True)
        (self.links / selection.FEED).mkdir()

    def install(self, command, **kwargs):
        self.assertEqual(command[:4], ['./scripts/feeds', 'install', '-p', selection.FEED])
        for recipe in command[4:]:
            (self.links / selection.FEED / recipe).symlink_to(self.tree / 'feeds' / selection.FEED / recipe)

    def test_replace_stale_proxy_source_keep_system_and_pinned_toolchain(self):
        stale = self.links / 'packages/sing-box'
        stale.symlink_to(self.tree / 'feeds/packages/net/sing-box')
        system = self.links / 'packages/openssl'
        system.symlink_to(self.tree / 'feeds/packages/libs/openssl')
        (self.links / 'golang').mkdir()
        pinned = self.links / 'golang/golang'
        pinned.symlink_to(self.tree / 'feeds/golang')
        with patch.object(selection.subprocess, 'run', side_effect=self.install):
            selection.select(self.tree)
        self.assertFalse(stale.is_symlink())
        self.assertTrue(system.is_symlink())
        self.assertTrue(pinned.is_symlink())
        selection.check_links(self.tree)
        stale.symlink_to(self.tree / 'feeds/packages/net/sing-box')
        with self.assertRaisesRegex(RuntimeError, 'Wrong source'):
            selection.check_links(self.tree)

    def test_missing_recipe_does_not_remove_existing_link(self):
        stale = self.links / 'packages/sing-box'
        stale.symlink_to(self.tree / 'feeds/packages/net/sing-box')
        (self.tree / 'feeds' / selection.FEED / 'sing-box/Makefile').unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            selection.select(self.tree)
        self.assertTrue(stale.is_symlink())

    def test_multi_binary_metadata_and_excluded_library(self):
        index = self.tree / 'index'
        index.write_text('Source-Makefile: feeds/openwrt_passwall_packages/v2ray-geodata/Makefile\n'
                         'Package: v2ray-geoip\nVersion: 20261008.1\n\n'
                         'Package: v2ray-geosite\nVersion: 20261009.1\n\n'
                         'Source-Makefile: feeds/openwrt_passwall_packages/openssl/Makefile\n'
                         'Package: libopenssl\nVersion: 9\n')
        packages = selection.feed_packages(index)
        self.assertEqual(set(packages), {'v2ray-geoip', 'v2ray-geosite'})
        self.assertEqual(packages['v2ray-geosite']['version'], '20261009.1')

    def test_release_rejects_old_missing_or_unbuilt_packages(self):
        report = self.tree / 'proxy-packages.json'
        report.write_text(json.dumps({'packages': {'sing-box': {'version': '1.14.3-r1'}}}))
        with self.assertRaisesRegex(RuntimeError, 'No firmware'):
            selection.verify(report, self.tree)
        manifest = self.tree / 'device.manifest'
        for content in ('sing-box - 1.14.0-r1\n', 'other - 1\n'):
            manifest.write_text(content)
            with self.assertRaisesRegex(RuntimeError, 'expected 1.14.3-r1'):
                selection.verify(report, self.tree)
        manifest.write_text('sing-box - 1.14.3-r1\n')
        selection.verify(report, self.tree)


if __name__ == '__main__':
    unittest.main()
