# PL7f, round 7: every open case (the conductor, 25 November 2026, 07:42 UTC)

From the verifier's record at tip `30833c83b5` (main merged in). **This round is the one row below and nothing else.**
Round 8 is the last the dial allows.

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **D234's planted second command is not at the real call's shape.** The "same docker run with a fourth mount" case puts the fourth `-v` after the image, where Docker would read it as the container's command; it is refused only because the argument count or the tail does not match, so nothing shows that **a real extra mount before the image** is refused (rule 15's second paragraph). | the exemption's test in `OspreyFlow_Build/tests/` (beside `local_docker_guard.py`'s) | Each planted command is the Caddy test's own argument list with exactly one real difference, in the place Docker reads it: (a) a fourth `-v <path>:<path>:ro` **among the mounts, before the image**; (b) one of the three mounts without `:ro`; (c) `--network` other than `none`; (d) no `--rm`; (e) another image tag. Each refused. Show the exemption matched on the image and mount count alone (a widened match) turning (a) and (b) green, so their red is for the reason claimed. The exact command stays allowed. |
