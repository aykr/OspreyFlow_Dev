# Demo lane handoff · closed after v0.6.0 (16 November 2026, 18:07Z)

**State.** govuk.ospreyflow.app runs v0.6.0 from `/opt/ospreyflow-v0.6.0` on ospreyflow-test (Compose project osprey-small).
It is PROTECTED (v060/RULINGS.md, 15 Nov ~22:15Z): no apply, restart, rebuild, settings or other change without the owner's word.
The full record: `REPORT_2026-11-16_v060.md` (steps, logs in `/root/rebuild-2026-11-16/`, decisions, the sheet's corrections).
The old osprey-small deploy handoff (13–15 Nov, `/opt/ospreyflow`) is kept as `HANDOFF_OSPREY_SMALL_2026-11-13.md`.

**Done.** The rebuild, steps 1–9: gate, four sign-ins, health, five synthetic packs, GB basemap and gazetteer (in four cases,
not PI), egress `any` on the demo datasets, the Demo visitor role, both backups, the recorded home pointed at `$NEW`, the
QUEUE line deleted. After the owner's key: status, models (key present), Gemini's budget 1,000,000 a day, Usage.

**Open (each the owner's word, a change to the protected demo):**
1. Gemini's model id is doubled: the test 404s on `models/gemini/gemini-3.8-flash`. Fix: `roles: {extraction: gemini-3.8-flash}`
   in `$NEW/osprey.yaml`, then `apply` with `OSPREYFLOW_HOME=/opt/ospreyflow-v0.6.0`.
2. The search index is empty (0 documents; rebuilt at install, before the packs): `exec -T api python -m scripts.rebuild_search_index`.
3. Then: Test the connection, one Gemini answer in PI naming gemini-3.8-flash, and whether hmp (gazetteer, egress `none`)
   refuses Gemini on sending (it is offered at the choice).
4. The way back to `/opt/ospreyflow` needs an `apply` there first (its generated files are the stray install's render).

**Never** run `OF $NEW …` without `OSPREYFLOW_HOME`, never print a secret, synthetic packs only.
**Last commits before this pause:** de7b47a (the Gemini checks), 0a413a8, 5e3739a. Nothing of mine is running.
