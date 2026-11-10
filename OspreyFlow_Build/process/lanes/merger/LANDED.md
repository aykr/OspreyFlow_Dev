# Merges the merger prepared (ADR-142 Amendment 7)

One line per merge commit the merger built, written inside that commit: `<main parent> <lane head> <lane> <step>`.
A commit cannot hold its own hash, so the merge is named by its two parents. `git log --first-parent main`
shows it as the one merge commit whose parents are exactly these; the merger's "land" message gives its hash.

da162e6 b6570fd case L3.H2
871a271 ea3ba26 rules-b T3
