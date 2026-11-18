			function valid_ip(c, n) {
				if (c ~ /\./) return 1
				if (c !~ /[A-Fa-f0-9]/ || c ~ /:::/ || c ~ /::.*::/) return 0
				n = gsub(/:/, ":", c)
				return (c ~ /::/) ? (n <= 7) : (n == 7)
			}
			function pick_ip(s, mode, m, res, c, pre, last) {
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
				$0 = gensub(/(^|[^A-Fa-f0-9:])::[Ff]{4}:(([0-9]{1,3}\.){3}[0-9]{1,3})/, "\\1\\2", "g", $0)
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
					if (cand !~ /^[0:]*(:0*1)?$/) {
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
