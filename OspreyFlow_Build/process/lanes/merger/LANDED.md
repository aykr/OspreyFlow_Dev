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
b4aaea6 e1b7626 docs D2c-p2
d507f9c 5585b4e platform P7b
586769e 87ee3ef studio-b L1.9p2
889884d f4b7370 case P9
eec25d1 d84bbe8 case-b P12p2
91a029c b061903 admin P10p2
62cfdbe 21fd158 docs D2c-p3
8f95d5a 69ef543 rules-b guides
5675103 7af3fc6 admin T1p5
61eb4c2 c929bc2 docs guides-links
5bc60ba d3db8d9 docs D2c-p4
b4b570d eaaa9d4 studio carries
5a8c2d8 eaede4c docs sites
9aff917 8b7a34d platform-b ci-green
a9af842 5ee595f platform-b gate-b+footer
680c86f 743069c platform-b stateless
2b088f9 - orchestrator home-facts-plain fix
4196468 30f4aa5 platform home-access
70a6e6f edc31e0 platform-b onepass
4f31f9d d0a3a70 platform-b rail+help
d935981 1aaa354 demo records
f78368e 8a51a92 platform-b ci-fixes
6db2a4a ea8e0f2 platform compact-govuk (+23c4fbd the merge's contrast entry rekeyed)
e0445ac e85e294 platform-b pin
2326bde 609e18e platform-b live records
635233f 2e023fa platform-b committed-yaml
5c862eb 3e701b7 rules lists (ADR-146 Am 7)
45dc4a3 9a90aa8 admin refresh (ADR-050 Am 3)
5e632a8 ad4fb4e platform-b budget-run
ddeb7d3 3f801b2 platform-b rule-editor race
a5afeef c41d7db platform-b ADR-135 Am 10
614ec43 00eb1d4 platform cli-deps (R1 finding 9)
e19a7db fed0752 platform-b modes (ADR-145 Am 13, ADR-144 Am 3)
78d1275 ec5d311 admin hb (stages + reorganised view)
60af8dc f117c35 admin lease-word fix
52ad2d8 b4712bf platform-b ci-small
