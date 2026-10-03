#!/usr/bin/env bash
set -euo pipefail

# Keep the tree at a stable path: built host tools can contain absolute paths.
build_root=${OPENWRT_BUILD_ROOT:-/home/ubuntu/build}
repo_url=${REPO_URL:-https://gh-proxy.com/github.com/openwrt/openwrt}
repo_branch=${REPO_BRANCH:-main}

target_tree() {
  case "$1" in
    acrh17.config|x86.config|mt6000.config)
      printf '%s/openwrt-%s\n' "$build_root" "${1%.config}"
      ;;
    *) echo "Unknown build configuration: $1" >&2; return 1 ;;
  esac
}

prepare_tree() {
  local tree
  tree=$(target_tree "$1")
  mkdir -p "$build_root"
  if [[ ! -d "$tree" ]]; then
    # Borrow Git objects, then dissociate so legacy cleanup cannot break this tree.
    local reference=()
    if [[ -d "$build_root/openwrt/.git" ]]; then
      reference=(--reference-if-able "$build_root/openwrt" --dissociate)
    fi
    git clone "${reference[@]}" --branch "$repo_branch" "$repo_url" "$tree"
  fi
  [[ -d "$tree/.git" ]] || { echo "Not an OpenWrt checkout: $tree" >&2; return 1; }
  cd "$tree"
  # Apply URL changes to persistent checkouts as well as newly cloned trees.
  git remote set-url origin "$repo_url"
  git fetch origin "$repo_branch"
  git reset --hard FETCH_HEAD
  # Refresh generated metadata and feed links, retaining compiled dependencies.
  git clean -ffdx -e /dl/ -e /.ccache/ -e /build_dir/ -e /staging_dir/ \
    -e /bin/ -e /feeds/ -e /.builder-cache/ -e '/key-build*'
  # Keep binary packages, but never publish images left by an earlier run.
  if [[ -d bin/targets ]]; then
    find bin/targets -mindepth 3 -maxdepth 3 -type f -delete
  fi

  # Remove the Go compatibility link before resetting its parent feed.
  if [[ -L feeds/packages/lang/golang ]]; then
    rm feeds/packages/lang/golang
  fi
  local feed
  for feed in feeds/*; do
    [[ -d "$feed/.git" ]] || continue
    git -C "$feed" reset --hard HEAD
    git -C "$feed" clean -ffdx
  done
  git log -1 --oneline
}

check_cache() {
  local tree signature
  local config_sources=()
  tree=$(target_tree "$1")
  cd "$tree"
  mapfile -d '' -t config_sources < <(find toolchain -type f -name 'Config*' -print0)
  # Package selections use OpenWrt's normal rebuild checks. Changes to compiler
  # recipes, host tools or toolchain options invalidate all dependent objects.
  signature=$({
    git ls-tree HEAD tools toolchain
    awk '
      FILENAME != ARGV[ARGC - 1] {
        if ($1 == "config" || $1 == "menuconfig") symbols["CONFIG_" $2] = 1
        next
      }
      {
        name = $1
        sub(/=.*/, "", name)
        if ($1 == "#") name = $2
        if (name in symbols || name ~ /^CONFIG_(TARGET_(BOARD|SUBTARGET|ARCH_PACKAGES|SUFFIX)|HOST_|OPTIMIZE_HOST_TOOLS|BUILD_SUFFIX|EXTRA_OPTIMIZATION|USE_APK)/) print
      }
    ' "${config_sources[@]}" .config | LC_ALL=C sort
  } | sha256sum | cut -d ' ' -f 1)
  if [[ ! -f .builder-cache/toolchain-signature ]] || \
    [[ $(cat .builder-cache/toolchain-signature) != "$signature" ]]; then
    echo 'Toolchain cache is new or incompatible; clearing compiled dependencies.'
    FORCE_UNSAFE_CONFIGURE=1 make dirclean
  fi
  mkdir -p .builder-cache
  printf '%s\n' "$signature" > .builder-cache/toolchain-signature
}

clean_trees() {
  local tree status=0
  # Include the original shared checkout while transitioning to isolated trees.
  for tree in "$build_root/openwrt-acrh17" "$build_root/openwrt-x86" \
    "$build_root/openwrt-mt6000" "$build_root/openwrt"; do
    [[ -d "$tree/.git" ]] || continue
    echo "Removing all build results and caches from $tree"
    if FORCE_UNSAFE_CONFIGURE=1 make -C "$tree" distclean; then
      rm -rf "$tree/.builder-cache"
    else
      status=1
    fi
  done
  return "$status"
}

case "${1:-}" in
  prepare) prepare_tree "${2:?Specify a configuration file}" ;;
  check-cache) check_cache "${2:?Specify a configuration file}" ;;
  clean) clean_trees ;;
  *) echo "Usage: $0 {prepare CONFIG|check-cache CONFIG|clean}" >&2; exit 1 ;;
esac
