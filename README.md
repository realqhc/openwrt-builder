# OpenWrt builder

Each matrix job updates OpenWrt `main` and all feeds before building. Source
versions are not pinned between automatic runs. Persistent checkouts in the
builder container are isolated by configuration:

| Configuration | Build directory |
| --- | --- |
| `acrh17.config` | `/home/ubuntu/build/openwrt-acrh17` |
| `x86.config` | `/home/ubuntu/build/openwrt-x86` |
| `mt6000.config` | `/home/ubuntu/build/openwrt-mt6000` |

The first run creates each checkout and compiles it from scratch. Existing build
objects are not moved from the legacy `/home/ubuntu/build/openwrt`: host tools
can embed their original absolute paths. New checkouts borrow Git objects from
the legacy checkout when available, then dissociate from it.

The trees share `/home/ubuntu/build/dl` through their `dl` symlinks. Source
archives, Go module downloads and Cargo caches can be reused across targets.
Cargo's mirror configuration is written to the shared `dl/cargo/config.toml`.
Build outputs, staging directories and feeds stay isolated at their existing
absolute paths.

Subsequent runs retain `build_dir`, `staging_dir`, binary packages, downloads,
feeds, signing keys and ccache. OpenWrt checks which packages need rebuilding.
Changes to host-tool/toolchain sources or compiler configuration trigger
`make dirclean` to rebuild dependent objects. Unchanged Go sources are kept in a
separate feed on branch `27.x` (Go 1.27.2 at the time of this change), meeting
Tailscale 1.104.1's Go 1.27.1 minimum. Sing-box 1.14.0 no longer uses the old
`go-json-experiment` dependency that required the earlier Go 1.26 pin.
Old firmware files are removed before building;
uploads are copied into the runner workspace without deleting binary packages.

Source extraction uses the make command-line setting
`TAR="env TAR_OPTIONS=--no-same-owner tar"`, preserving OpenWrt's extraction
flags and old-style `tar xvf` calls while avoiding archive ownership changes
inside nspawn. The full extraction flags must not be passed through make's
`TAR_OPTIONS`: GNU tar would also read them from the environment and apply
`-f` twice. This does not modify upstream `include/unpack.mk`.

Rust uses the feed's original build configuration, which
already disables CI LLVM downloads; no local Rust Makefile patch is applied.

Both workflows share one GitHub Actions concurrency group, with cancellation
disabled. Matrix jobs run one at a time on the current builder. Cleanup waits
for an active build to finish, and builds wait for active cleanup.

The existing quarterly cleanup schedule runs `make distclean` in all three
checkouts and the legacy checkout, if present. It removes **all build outputs,
feeds, ccache and generated signing keys**, while retaining the Git checkouts.
Each tree's `dl` symlink is unlinked; the shared downloads and Cargo cache are
deleted once after every tree cleans successfully. The next build updates
sources and rebuilds from scratch. Manual preparation, migration, builds and
cleanup inside the container must only run while Actions is idle.

For existing installations, merge downloads once while all builds are idle:

```bash
bash scripts/build-tree.sh migrate-downloads
```

This merges all three target caches and the legacy checkout's cache into the
common directory, then replaces their `dl` folders with symlinks. Existing
common files are retained; unfinished downloads and Cargo lock/database files
are skipped. Go module sources are re-extracted from their cached download
archives. A failed copy leaves the source directory intact. Repeating the
command is safe, and future preparation creates the links for new checkouts.

The helper can also be run manually with `OPENWRT_BUILD_ROOT` set to a scratch
directory for validation:

```bash
bash scripts/build-tree.sh prepare x86.config
# After applying feeds and DIY scripts:
make -C "${OPENWRT_BUILD_ROOT:-/home/ubuntu/build}/openwrt-x86" defconfig 'TAR=env TAR_OPTIONS=--no-same-owner tar'
bash scripts/build-tree.sh check-cache x86.config
# Destructive: clears all build results and caches in the managed checkouts.
bash scripts/build-tree.sh clean
```

This is an incremental source build. SDK and ImageBuilder generation are not
enabled by these workflows.

Run the cache migration and cleanup regression checks with
`python3 scripts/test-build-tree.py`.
