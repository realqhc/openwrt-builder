# SPDX-License-Identifier: GPL-3.0-or-later
# banIP 1.9.1-2 log parser from openwrt/packages at 770d4058b06f09d4c16321ca53401454f148095e.

			function pick_ip(s, mode, m, res) {
				res = ""
				while (match(s, /([0-9]{1,3}\.){3}[0-9]{1,3}|([A-Fa-f0-9]{0,4}:){2,7}[A-Fa-f0-9]{0,4}/, m)) {
					res = m[0]
					if (mode == "first") break
					s = substr(s, RSTART + RLENGTH)
				}
				return res
			}
			function anchor_for(line, k) { for (k = 1; k <= nterm; k++) if (line ~ pat[k]) return anc[k]; return "last" }
			BEGIN {
				unique = 0
				map = ENVIRON["ban_logterm_map"]
				n = split(map, recs, "\036")
				nterm = 0
				all_last = 1
				for (i = 1; i <= n; i++) {
					if (recs[i] == "") continue
					split(recs[i], f, "\037")
					nterm++
					anc[nterm] = f[1]
					pat[nterm] = f[2]
					if (f[1] != "last") all_last = 0
				}
			}
			{
				pos = all_last ? "last" : anchor_for($0)
				$0 = gensub(/(([0-9]{1,3}\.){3}[0-9]{1,3}):[0-9]+/, "\\1", "g", $0)
				sub(/\]:[0-9]+/, "]", $0)
				gsub(/[<>[\]]/, "", $0)
				ip = ""
				proto = ""
				cand = pick_ip($0, pos)
				if (cand ~ /\./) {
					if (cand !~ /^127\./ && cand !~ /^0\./) {
						ip = cand
						proto = ".v4"
					}
				} else if (cand ~ /:/) {
					sub(/%.*/, "", cand)
					if (cand !~ /^[0-9]{1,2}:[0-9]{1,2}:[0-9]{1,2}$/ && cand !~ /^([A-Fa-f0-9]{2}:){5}[A-Fa-f0-9]{2}$/) {
						ip = cand
						proto = ".v6"
					}
				}
				if (!ip) {
					next
				}
				cnt[ip]++
				if (cnt[ip] == 1) {
					unique++
					if (unique >= limit) {
						delete cnt
						unique = 0
						print "RESET"
						fflush()
					}
				}
				if (cnt[ip] == threshold) {
					print "BLOCK " ip " " proto
					fflush()
					delete cnt[ip]
					unique--
				}
			}
