#!/usr/bin/env python3
"""Select reviewed Passwall recipes and verify the packages shipped in images."""

import argparse
import json
from pathlib import Path
import subprocess


FEED = "openwrt_passwall_packages"
# Recipe names, including recipes producing several binary packages. New feed
# additions must be reviewed here; never prefer an entire feed of unknown scope.
RECIPES = (
    "chinadns-ng", "dns2socks", "geoview", "hysteria", "ipt2socks",
    "microsocks", "naiveproxy", "shadow-tls", "shadowsocks-rust",
    "shadowsocksr-libev", "simple-obfs", "sing-box", "tcping",
    "v2ray-geodata", "v2ray-plugin", "xray-core", "xray-plugin",
)


def check_links(tree):
    for recipe in RECIPES:
        expected = (tree / "feeds" / FEED / recipe).resolve()
        links = list((tree / "package/feeds").glob(f"*/{recipe}"))
        if len(links) != 1 or not links[0].is_symlink() or links[0].resolve() != expected:
            raise RuntimeError(f"Wrong source for {recipe}: {links}; expected {expected}")


def select(tree):
    # Validate everything before removing any generated package links.
    for recipe in RECIPES:
        if not (tree / "feeds" / FEED / recipe / "Makefile").is_file():
            raise RuntimeError(f"Required Passwall recipe missing: {recipe}")
    links = [p for name in RECIPES for p in (tree / "package/feeds").glob(f"*/{name}")]
    for link in links:
        if not link.is_symlink():
            raise RuntimeError(f"Refusing to remove non-symlink package: {link}")
    for link in links:
        link.unlink()
    # Feed install does not replace an already installed feed recipe, even -f.
    (tree / "tmp/.packageinfo").unlink(missing_ok=True)
    subprocess.run(["./scripts/feeds", "install", "-p", FEED, *RECIPES], cwd=tree, check=True)
    check_links(tree)


def feed_packages(index):
    source = package = None
    result = {}
    for line in index.read_text().splitlines():
        if line.startswith("Source-Makefile: "):
            source = Path(line.split(": ", 1)[1]).parent.name
            package = None
        elif line.startswith("Package: "):
            package = line.split(": ", 1)[1]
        elif line.startswith("Version: ") and package and source in RECIPES:
            result[package] = {"recipe": source, "version": line.split(": ", 1)[1]}
    return result


def record(tree, output):
    check_links(tree)
    packages = feed_packages(tree / "feeds" / f"{FEED}.index")
    selected = {
        line[len("CONFIG_PACKAGE_"):-2]
        for line in (tree / ".config").read_text().splitlines()
        if line.startswith("CONFIG_PACKAGE_") and line.endswith("=y")
    }
    if "sing-box" not in packages or "sing-box" not in selected:
        raise RuntimeError("Expected sing-box package is missing from the feed or configuration")
    shipped = {name: data for name, data in sorted(packages.items()) if name in selected}
    revision = subprocess.check_output(
        ["git", "-C", str(tree / "feeds" / FEED), "rev-parse", "HEAD"], text=True
    ).strip()
    result = {"feed": FEED, "revision": revision, "packages": shipped}
    output.write_text(json.dumps(result, indent=2) + "\n")
    for name, data in shipped.items():
        print(f"{name}: {FEED}/{data['recipe']} {data['version']} ({revision})")


def verify(report, directory):
    expected = json.loads(report.read_text())["packages"]
    manifests = sorted(directory.glob("*.manifest"))
    if not manifests:
        raise RuntimeError(f"No firmware manifests in {directory}")
    for manifest in manifests:
        actual = dict(line.split(" - ", 1) for line in manifest.read_text().splitlines() if " - " in line)
        for name, data in expected.items():
            if actual.get(name) != data["version"]:
                raise RuntimeError(
                    f"{manifest.name}: {name} expected {data['version']}, got {actual.get(name, 'MISSING')}"
                )
        print(f"Verified {len(expected)} Passwall packages in {manifest.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("select", "record", "verify"))
    parser.add_argument("--tree", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, default=Path("proxy-packages.json"))
    parser.add_argument("--images", type=Path)
    args = parser.parse_args()
    if args.action == "select":
        select(args.tree.resolve())
    elif args.action == "record":
        record(args.tree.resolve(), args.report)
    else:
        if args.images is None:
            parser.error("verify requires --images")
        verify(args.report, args.images)


if __name__ == "__main__":
    main()
