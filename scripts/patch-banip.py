#!/usr/bin/env python3
"""Fix bracketed IPv6 log peers in the banIP package before compilation."""
import argparse
from pathlib import Path
import re

OLD = r'sub(/\]:[0-9]+/, "]", $0)'
NEW = r'sub(/\]:[0-9]+:?/, "] ", $0)'


def patch(tree: Path) -> None:
    package = tree / 'feeds/packages/net/banip'
    source = package / 'files/banip-functions.sh'
    if not source.is_file():
        raise SystemExit('banIP source missing; run after updating the packages feed')
    text = source.read_text()
    if NEW in text and OLD not in text:
        print('banIP IPv6 peer fix already present')
        return
    if text.count(OLD) != 1:
        raise SystemExit('Unrecognized banIP peer parser; review upstream before building')
    makefile = package / 'Makefile'
    recipe = makefile.read_text()
    # Persistent build trees retain package artifacts. A distinct release forces
    # the modified package to replace an unpatched package of the same version.
    recipe, count = re.subn(r'^(PKG_RELEASE:=)([0-9]+(?:\.[0-9]+)*)$',
                            r'\g<1>\g<2>.1', recipe, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit('Unrecognized banIP package release; no files changed')
    source.write_text(text.replace(OLD, NEW))
    makefile.write_text(recipe)
    print('Applied banIP bracketed IPv6 peer fix and bumped package release')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tree', nargs='?', type=Path, default=Path.cwd())
    patch(parser.parse_args().tree)
