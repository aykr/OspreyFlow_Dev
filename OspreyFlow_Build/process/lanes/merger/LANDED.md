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
9b80f1a da5daf4 platform R1
6aa02ff 21056ce admin pg (ADR-114 Am 43) + ci-pg.diff
ad55522 1162de4 platform poc-rds (4b, ADR-114 Am 46)
aa90de3 00ba7c7 rules lists-audit
ee440c1 5d0999d admin v052-heartbeat
d2312e8 c4b955e rules stack-opensearch
8728dc6 f89f6d7 platform-b ci-recipe
8d6a898 a386fe3 docs v052-sweep part one (v0.5.1)
f5a6f3d fcdfec4 rules deps-opensearch (v0.5.2)
19e28e1 6b4bb26 platform v052-manifest (v0.5.2, step 2)
72c9303 89816c8 platform v052-datasafety (v0.5.2, step 3a and audit ruling 3)
258b510 7ca69aa docs v052-sweep D2/D3/D8
89ee482 528fef4 platform-b hygiene (v0.5.2)
7addbe6 f630917 admin hb2 (the heartbeat's stages per step, names and built count)
daa2733 58d2ea0 case v052-fixes (v0.5.2 step 3e and Part B), with its shared-files diff
f7891fb e5fab5a platform-b caddy-mark (main's NEEDS_CADDY red)
b9957c7 f896864 platform v052-backupsfix (main's seven Helm reds)
ad4cc89 3de0896 platform v052-runbookclaims
5178332 82504af platform v052-bedrockkeys
661a588 14f7680 rules-b v052D (Part D), with audit, spec03, registry and bar patches
b1d1f07 e73ecc0 case-b v052-r1-driver (step 6's driver)
cf09c42 5e89793 platform v052-searchkind, with v052-standin
7af832b 425a54a platform v052-pgmemory (main's render-memory red)
2b8c642 5f0f64e case-b v052-selection (Parts C and E), with tokens, registry and every-harness diffs
d97dde2 5f2aec7 docs 6a8 (main's 6a8 red), admin guide PDF reprinted
7a0cad7 c3f4600 docs 6a8-shared, admin guide PDF reprinted (1.96)
6c35698 60eca34 case-b budget (timed unit cases run alone)
beff3b6 b68a513 admin v052 (step 3b's identities)
036a861 21f729d docs v052D-user (user guide §6, 1.52), PDF reprinted
5be78c3 ffda1d9 platform-b v052-gate (step 3b, Superset and report sync), admin guide PDF reprinted (1.97)
1e88cfce 87d1689 platform v052-r1reporting
8acbc29 c626a5b docs spec10 (the guide's two copies held as one)
f193666 e00a09c platform v052-r1upgrade
8412c67 6fcdb62 admin idp-labels, with stack_lease_reap.diff
b925385 cb54a90 case-b lease-tests, with its stack_lease.sh diff
1d331f8 e28565f case-b npm-lock, with its stack_lease.sh diff
2d3fe2f 6d1a5cf rules-b analytics-field (A7's 500)
8a5bde1 0b480e8 platform-b v052-r1 (step 6's run sheet and checks)
428e993 7568835 platform-b v052-rls (the guest token's RLS read)
fd96c11 d8971cd platform-b v052-sheet
4116841 252df74 admin audit1 (ruling 1, option A), three guide PDFs reprinted
296ab81 a46e2ee rules v052-index (step 3c), with v052-index_ci_yml.diff (the owner's word)
c1373da 7ba5f37 studio v052-search (step 3d), with its two diffs (the owner's word)
822a2fb 859ca7d case-b install-pending (spec 08 halves; CI's over-the-wire job proves the seeded halves)
fa383e5 3ad0803 docs 6a-upgrade (1.99), PDF reprinted
d8888d8 2730b69 docs 6a-search (2.00), PDF reprinted
c42c1e4 9f22c21 platform-b v051-upg (the rehearsal, the real update and its rollback)
77ee8fb e964d4c platform-b v052-dayplan
175776c a86a9c1 docs v052-admin-fixes (2.01), PDF reprinted
