# Merges the merger prepared (ADR-142 Amendment 7)

One line per merge commit the merger built, written inside that commit: `<main parent> <lane head> <lane> <step>`.
A commit cannot hold its own hash, so the merge is named by its two parents. `git log --first-parent main`
shows it as the one merge commit whose parents are exactly these; the merger's "land" message gives its hash.

da162e6 b6570fd case L3.H2
871a271 ea3ba26 rules-b T3
70a3bc5 85f2447 studio-b L1.10b
7b39106 75cbc9b admin T1p4
c835b9d 373b3dd rules hyg
e7e398e f262e7b docs D2d
cc82f23 5b06ad4 studio-b L1.9p1
1684f12 5357223 platform P7
8aa3da5 fb6b02c docs D2c-p1
44207f9 b716e9c platform-b P11p1
0878f37 f165de2 platform-b carries
3af901d 88c78c3 case-b P12p1
9e5c705 021ee42 platform-b P11p2
77784af 2102d21 rules-b T3b
f78b307 5ef24c6 admin P10p1
