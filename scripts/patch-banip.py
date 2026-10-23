#!/usr/bin/env python3
"""Preserve log peer address boundaries in banIP before compilation."""
import argparse
from pathlib import Path
import re

OLD_PICK = r'''			function pick_ip(s, mode, m, res) {
				res = ""
				while (match(s, /([0-9]{1,3}\.){3}[0-9]{1,3}|([A-Fa-f0-9]{0,4}:){2,7}[A-Fa-f0-9]{0,4}/, m)) {
					res = m[0]
					if (mode == "first") break
					s = substr(s, RSTART + RLENGTH)
				}
				return res
			}
'''

NEW_PICK = r'''			function pick_ip(s, mode, m, res) {
				res = ""
				# Match bracketed peers as a unit to preserve address boundaries.
				while (match(s, peer_re, m)) {
					res = m[1] != "" ? m[1] : m[0]
					if (res ~ /\./) sub(/:[0-9]+$/, "", res)
					if (mode == "first") break
					s = substr(s, RSTART + RLENGTH)
				}
				return res
			}
'''

OLD_BEGIN = r'''			BEGIN {
				unique = 0
'''

NEW_BEGIN = r'''			BEGIN {
				ipv4 = "([0-9]{1,3}\\.){3}[0-9]{1,3}"
				ipv6 = "([A-Fa-f0-9]{0,4}:){2,7}[A-Fa-f0-9]{0,4}"
				peer_re = "\\[(" ipv4 "|" ipv6 ")(%[[:alnum:]_.-]+)?\\](:[0-9]+)?|" ipv4 "(:[0-9]+)?|" ipv6
				unique = 0
'''

OLD_NORMALIZE = r'''				$0 = gensub(/(([0-9]{1,3}\.){3}[0-9]{1,3}):[0-9]+/, "\\1", "g", $0)
				sub(/\]:[0-9]+/, "]", $0)
				gsub(/[<>[\]]/, "", $0)
'''

LEGACY_NORMALIZE = r'''				$0 = gensub(/(([0-9]{1,3}\.){3}[0-9]{1,3}):[0-9]+/, "\\1", "g", $0)
				sub(/\]:[0-9]+:?/, "] ", $0)
				gsub(/[<>[\]]/, "", $0)
'''


def patch(tree: Path) -> None:
    package = tree / 'feeds/packages/net/banip'
    source = package / 'files/banip-functions.sh'
    if not source.is_file():
        raise SystemExit('banIP source missing; run after updating the packages feed')
    text = source.read_text()
    if (text.count(NEW_PICK) == 1 and text.count(NEW_BEGIN) == 1
            and OLD_PICK not in text and OLD_NORMALIZE not in text
            and LEGACY_NORMALIZE not in text):
        print('banIP peer extraction fix already present')
        return
    normalizers = [block for block in (OLD_NORMALIZE, LEGACY_NORMALIZE)
                   if text.count(block) == 1]
    if (text.count(OLD_PICK) != 1 or text.count(OLD_BEGIN) != 1
            or NEW_PICK in text or NEW_BEGIN in text
            or len(normalizers) != 1
            or text.count(OLD_NORMALIZE) + text.count(LEGACY_NORMALIZE) != 1):
        raise SystemExit('Unrecognized banIP peer parser; review upstream before building')
    makefile = package / 'Makefile'
    recipe = makefile.read_text()
    # Use a new suffix so persistent trees cannot reuse the earlier .1 fix.
    recipe, count = re.subn(r'^(PKG_RELEASE:=)([0-9]+(?:\.[0-9]+)*)$',
                            r'\g<1>\g<2>.2', recipe, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit('Unrecognized banIP package release; no files changed')
    patched = (text.replace(OLD_PICK, NEW_PICK)
               .replace(OLD_BEGIN, NEW_BEGIN)
               .replace(normalizers[0], ''))
    source.write_text(patched)
    makefile.write_text(recipe)
    print('Applied banIP peer extraction fix and bumped package release')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tree', nargs='?', type=Path, default=Path.cwd())
    patch(parser.parse_args().tree)
