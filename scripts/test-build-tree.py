#!/usr/bin/env python3
"""Exercise cache migration and cleanup using disposable build trees."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/build-tree.sh"
TREES = ("openwrt-acrh17", "openwrt-x86", "openwrt-mt6000", "openwrt")


class DownloadCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="openwrt-cache-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "dl"
        self.env = dict(os.environ, OPENWRT_BUILD_ROOT=str(self.root))

    def run_helper(self, *args, check=True):
        return subprocess.run(
            ["bash", str(HELPER), *args], env=self.env,
            text=True, capture_output=True, check=check,
        )

    def tree(self, name):
        tree = self.root / name
        (tree / ".git").mkdir(parents=True)
        for directory in ("dl", "build_dir", "staging_dir", "feeds"):
            (tree / directory).mkdir()
            (tree / directory / "keep").write_text(directory)
        (tree / "Makefile").write_text(
            "distclean:\n\trm -rf dl build_dir staging_dir feeds\n"
        )
        return tree

    def test_merge_repeat_and_cleanup(self):
        trees = [self.tree(name) for name in TREES]
        self.cache.mkdir()
        (self.cache / "existing.tar.gz").write_text("keep existing")
        for number, tree in enumerate(trees):
            (tree / "dl" / f"source-{number}.tar.gz").write_text(str(number))
            (tree / "dl/existing.tar.gz").write_text("other cached copy")
            (tree / "dl/unfinished.tar.gz.dl").write_text("partial")
            (tree / "dl/unfinished.tar.gz.hash").write_text("partial")
            (tree / "dl/cargo/registry/cache/mirror").mkdir(parents=True)
            (tree / "dl/cargo/registry/cache/mirror/pkg.crate").write_text("crate")
            (tree / "dl/cargo/.global-cache").write_text("process state")
            (tree / "dl/cargo/.package-cache").write_text("lock")
            (tree / "dl/go-mod-cache/cache/download").mkdir(parents=True)
            (tree / "dl/go-mod-cache/cache/download/pkg.zip").write_text("module")
            (tree / "dl/go-mod-cache/unfinished-module").mkdir()
            (tree / "dl/go-mod-cache/unfinished-module/source.go").write_text("partial extraction")
        self.run_helper("migrate-downloads")
        self.run_helper("migrate-downloads")
        self.assertEqual((self.cache / "existing.tar.gz").read_text(), "keep existing")
        self.assertEqual(len(list(self.cache.glob("source-*.tar.gz"))), 4)
        self.assertFalse(list(self.cache.glob("*.dl")))
        self.assertFalse(list(self.cache.glob("*.hash")))
        self.assertFalse((self.cache / "cargo/.global-cache").exists())
        self.assertFalse((self.cache / "cargo/.package-cache").exists())
        self.assertEqual((self.cache / "cargo/registry/cache/mirror/pkg.crate").read_text(), "crate")
        self.assertEqual((self.cache / "go-mod-cache/cache/download/pkg.zip").read_text(), "module")
        self.assertFalse((self.cache / "go-mod-cache/unfinished-module").exists())
        for tree in trees:
            self.assertTrue((tree / "dl").is_symlink())
            self.assertEqual((tree / "dl").resolve(), self.cache)
            for directory in ("build_dir", "staging_dir", "feeds"):
                self.assertEqual((tree / directory / "keep").read_text(), directory)
        result = self.run_helper("clean")
        self.assertEqual(result.stdout.count("Removing shared downloads"), 1)
        self.assertFalse(self.cache.exists())
        self.assertTrue(all((tree / ".git").exists() for tree in trees))
        self.assertTrue(all(not (tree / "dl").is_symlink() for tree in trees))

    def test_failed_copy_preserves_source(self):
        tree = self.tree(TREES[0])
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        rsync = fake_bin / "rsync"
        rsync.write_text("#!/bin/sh\nexit 23\n")
        rsync.chmod(0o755)
        self.env["PATH"] = f"{fake_bin}:{self.env['PATH']}"
        result = self.run_helper("migrate-downloads", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((tree / "dl").is_symlink())
        self.assertEqual((tree / "dl/keep").read_text(), "dl")

    def test_failed_cleanup_preserves_shared_cache(self):
        tree = self.tree(TREES[0])
        self.run_helper("migrate-downloads")
        (tree / "Makefile").write_text("distclean:\n\tfalse\n")
        self.assertNotEqual(self.run_helper("clean", check=False).returncode, 0)
        self.assertEqual((self.cache / "keep").read_text(), "dl")

    def test_cargo_config_uses_shared_home(self):
        trees = [self.tree(name) for name in TREES[:3]]
        self.run_helper("migrate-downloads")
        workflow = (ROOT / ".github/workflows/build-openwrt.yml").read_text()
        block = workflow.split("      - name: Configure Cargo registry mirror\n", 1)[1]
        block = block.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
        script = "\n".join(line[10:] for line in block.splitlines())
        workspace = self.root / "workspace"
        workspace.mkdir()
        (workspace / "openwrt").symlink_to(trees[0])
        env = dict(self.env, OPENWRT_DL_DIR=str(self.cache))
        subprocess.run(["bash", "-eu", "-c", script], cwd=workspace, env=env, check=True)
        config = self.cache / "cargo/config.toml"
        self.assertIn('replace-with = "ustc"', config.read_text())
        self.assertTrue(all((tree / "dl/cargo/config.toml").samefile(config) for tree in trees))

    def test_prepare_preserves_shared_cache_across_git_clean(self):
        upstream = self.root / "upstream"
        subprocess.run(["git", "init", "-b", "main", str(upstream)], check=True, capture_output=True)
        (upstream / "README").write_text("fixture")
        subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
        subprocess.run([
            "git", "-C", str(upstream), "-c", "user.name=Cache Test",
            "-c", "user.email=test@example.invalid", "commit", "-m", "Fixture",
        ], check=True, capture_output=True)
        self.env.update(REPO_URL=str(upstream), REPO_BRANCH="main")
        self.run_helper("prepare", "x86.config")
        (self.cache / "source.tar.gz").write_text("cached source")
        self.run_helper("prepare", "x86.config")
        self.assertEqual((self.root / "openwrt-x86/dl").resolve(), self.cache)
        self.assertEqual((self.cache / "source.tar.gz").read_text(), "cached source")


if __name__ == "__main__":
    unittest.main()
