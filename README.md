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

Subsequent runs retain `build_dir`, `staging_dir`, binary packages, downloads,
feeds, signing keys and ccache. OpenWrt checks which packages need rebuilding.
Changes to host-tool/toolchain sources or compiler configuration trigger
`make dirclean` to rebuild dependent objects. Unchanged Go sources are kept in a
separate feed on branch `26.x`. Old firmware files are removed before building;
uploads are copied into the runner workspace without deleting binary packages.

Source extraction uses the make command-line setting
`TAR_OPTIONS="-xf - --no-same-owner"`, preserving normal extraction flags while
avoiding archive ownership changes inside nspawn. It does not modify upstream
`include/unpack.mk`. Rust uses the feed's original build configuration, which
already disables CI LLVM downloads; no local Rust Makefile patch is applied.

Both workflows share one GitHub Actions concurrency group, with cancellation
disabled. Matrix jobs run one at a time on the current builder. Cleanup waits
for an active build to finish, and builds wait for active cleanup.

The existing quarterly cleanup schedule runs `make distclean` in all three
checkouts and the legacy checkout, if present. It removes **all build outputs,
downloads, feeds, ccache and generated signing keys**, while retaining the Git
checkouts. The next build updates sources and rebuilds from scratch. Manual
builds or cleanup inside the container should only run while Actions is idle.

The helper can also be run manually with `OPENWRT_BUILD_ROOT` set to a scratch
directory for validation:

```bash
bash scripts/build-tree.sh prepare x86.config
# After applying feeds and DIY scripts:
make -C "${OPENWRT_BUILD_ROOT:-/home/ubuntu/build}/openwrt-x86" defconfig 'TAR_OPTIONS=-xf - --no-same-owner'
bash scripts/build-tree.sh check-cache x86.config
# Destructive: clears all build results and caches in the managed checkouts.
bash scripts/build-tree.sh clean
```

This is an incremental source build. SDK and ImageBuilder generation are not
enabled by these workflows.
