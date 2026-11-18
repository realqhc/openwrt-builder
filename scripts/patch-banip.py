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


R5_PICK = r'''			function pick_ip(s, mode, m, res, c, pre, last) {
				res = ""
				last = " "
				while (match(s, /([0-9]{1,3}\.){3}[0-9]{1,3}|([A-Fa-f0-9]{0,4}:){2,7}[A-Fa-f0-9]{0,4}/, m)) {
					c = m[0]
					pre = (RSTART > 1) ? substr(s, RSTART - 1, 1) : last
					last = substr(c, length(c), 1)
					s = substr(s, RSTART + RLENGTH)
					if (c ~ /^:[^:]/) {
						c = substr(c, 2)
						pre = ":"
					}
					if (c ~ /[^:]:$/) c = substr(c, 1, length(c) - 1)
					if (pre ~ /[A-Za-z0-9_]/ || !valid_ip(c)) continue
					res = c
					if (mode == "first") break
				}
				return res
			}
'''

# Keep upstream address validation and apply its boundary checks to bare addresses.
R5_NEW_PICK = r'''			function pick_ip(s, mode, m, res, c, pre, last) {
				res = ""
				last = " "
				while (match(s, peer_re, m)) {
					c = m[1] != "" ? m[1] : m[0]
					pre = (RSTART > 1) ? substr(s, RSTART - 1, 1) : last
					last = substr(m[0], RLENGTH, 1)
					s = substr(s, RSTART + RLENGTH)
					if (m[1] != "") {
						pre = "["
					} else if (c ~ /\./) {
						sub(/:[0-9]+$/, "", c)
					} else {
						if (c ~ /^:[^:]/) {
							c = substr(c, 2)
							pre = ":"
						}
						if (c ~ /[^:]:$/) c = substr(c, 1, length(c) - 1)
					}
					if (pre ~ /[A-Za-z0-9_]/ || !valid_ip(c)) continue
					res = c
					if (mode == "first") break
				}
				return res
			}
'''

R5_NORMALIZE = r'''				$0 = gensub(/(^|[^A-Fa-f0-9:])::[Ff]{4}:(([0-9]{1,3}\.){3}[0-9]{1,3})/, "\\1\\2", "g", $0)
				sub(/\]:[0-9]+/, "]", $0)
				gsub(/[<>[\]]/, "", $0)
'''

R5_NEW_NORMALIZE = r'''				$0 = gensub(/(^|[^A-Fa-f0-9:])::[Ff]{4}:(([0-9]{1,3}\.){3}[0-9]{1,3})/, "\\1\\2", "g", $0)
				gsub(/[<>]/, " ", $0)
'''


def patch(tree: Path) -> None:
    package = tree / 'feeds/packages/net/banip'
    source = package / 'files/banip-functions.sh'
    if not source.is_file():
        raise SystemExit('banIP source missing; run after updating the packages feed')
    text = source.read_text()
    changes = (
        (OLD_PICK, NEW_PICK, OLD_NORMALIZE, ''),
        (OLD_PICK, NEW_PICK, LEGACY_NORMALIZE, ''),
        (R5_PICK, R5_NEW_PICK, R5_NORMALIZE, R5_NEW_NORMALIZE),
    )
    pickers = {block for old, new, _, _ in changes for block in (old, new)}
    normalizers = {block for _, _, old, new in changes for block in (old, new) if block}
    picker_count = sum(text.count(block) for block in pickers)
    normalizer_count = sum(text.count(block) for block in normalizers)
    already_patched = (
        picker_count == 1 and text.count(NEW_BEGIN) == 1 and OLD_BEGIN not in text
        and ((NEW_PICK in text and normalizer_count == 0)
             or (R5_NEW_PICK in text and R5_NEW_NORMALIZE in text and normalizer_count == 1))
    )
    change = next((entry for entry in changes if entry[0] in text and entry[2] in text), None)
    if not already_patched and (
        change is None or picker_count != 1 or normalizer_count != 1
        or text.count(OLD_BEGIN) != 1 or NEW_BEGIN in text
    ):
        raise SystemExit('Unrecognized banIP peer parser; review upstream before building')
    makefile = package / 'Makefile'
    recipe = makefile.read_text()
    # APK requires an integer revision. Migrate only suffixes emitted by our
    # previous patches, preserving the original upstream release as the base.
    releases = re.findall(r'^PKG_RELEASE:=(.*)$', recipe, flags=re.MULTILINE)
    match = re.fullmatch(r'([0-9]+)(\.1(?:\.2)?|\.2)?', releases[0]) if len(releases) == 1 else None
    if match is None:
        raise SystemExit('Unrecognized banIP package release; no files changed')
    if already_patched and match[2] is None:
        print('banIP peer extraction fix already present')
        return
    release = str(int(match[1]) + 1)
    recipe = re.sub(r'^PKG_RELEASE:=.*$', 'PKG_RELEASE:=' + release,
                    recipe, flags=re.MULTILINE)
    if not already_patched:
        picker, new_picker, normalizer, new_normalizer = change
        source.write_text(text.replace(picker, new_picker)
                          .replace(OLD_BEGIN, NEW_BEGIN)
                          .replace(normalizer, new_normalizer))
    makefile.write_text(recipe)
    print('Applied banIP peer extraction fix and bumped package release')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tree', nargs='?', type=Path, default=Path.cwd())
    patch(parser.parse_args().tree)
