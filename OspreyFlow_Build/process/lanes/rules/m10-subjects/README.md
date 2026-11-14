# M10's subjects of their case's unit (`scripts.client_size_leaks`)

Step 4's first M10 runs on stack d (14 November 2026, runs 20261114T142209Z-ac9b7665 masked,
20261114T143128Z-b807546c masked, 20261114T143856Z-516ef319 unmasked at platform's 8ba5ed6) refused
every case at the case: "the cleared principal's answer does not name HTTPError: HTTP Error 404: Not
Found". The Conduit opens a case only to a principal whose `org_unit` is the case's `owning_unit`,
whatever it is granted (`services/api/investigations.py`, `WHERE i.id = $1 AND i.owning_unit = $2`;
ADR-036's boundary, working as built). B's M10 files chose each control by the record-level rule
alone (`principal_may_read`), so unit-fiu's and unit-intel-covert's controls could not open the
unit-intel case, nor unit-fiu the partner cases of unit-comms, unit-records and unit-economic; and
`m10-part`, of unit-records, could not open the intelligence reports' case either (the 25 cs-covert
cases' 404). Nothing hidden was reached, so nothing was learned about leaks, either way. The
orchestrator approved the fix below on 14 November.

## The fix (Prompt L: the strict option for access, listed to overrule)

- **`m10-part` is of the measure case's unit**: unit-intel, OFFICIAL-SENSITIVE, codes P C (it was
  unit-records). Its grants are unchanged (viewer of the intelligence reports' case).
- **Each control is `m10-cleared-<the unit of the case it searches>`**, SECRET, codes P C R: for the
  leak cases the intelligence reports' case's (`m10-cleared-unit-intel`), for a never-join case its
  partner case's. A case's unit is its source's marking's (`load_client_size`'s cases stage makes
  the case's `owning_unit` so; `case_units`).
- **A record nobody who opens its case may read is no case**: left out and counted
  (`counts.json`'s `leaks_kept_out`, `never_join_kept_out`), never given a control of another unit.
  The intelligence reports' SECRET/R reports are unit-intel-covert's, and code R is read only in its
  own unit, so no subject who opens the unit-intel case reads them: they leave the leak file, and
  they stay hidden from `m10-part` by its clearance.
- **The checks refuse a subject of another unit than the case it searches** (`_opens`, in
  `check_leaks` and `check_never_join`): "... is of unit-X, and the case it searches is unit-Y's:
  the case is opened only to its own unit, so the search is refused (404) and proves nothing".
- `counts.json` names each subject used and its claims (`subjects`), for step 4's issuer
  (`step4_stack.SUBJECTS`, platform's).

## Red first

`plants.py` here: S1 to S6, each red alone, built and restored green (`PLANTS_RECORD.offline.txt`).
S4 (the control drawn as before) and S6 (`m10-part` of unit-records) are red at the build: the
check refuses the generator's old shape before anything is written.

## On stack d, in rules' queue turn (after rules-b's am20), under rules' lease

1. The files again, from B's (`OspreyFlow_Core`, `PYTHONPATH=.:packages`):
   `python -m scripts.client_size_leaks --from ~/osprey-load/b-1.0 --out ~/osprey-load/m10 --limit 500`
   (the earlier files kept as `~/osprey-load/m10-before-units/`).
2. The new controls' grants, viewer on their own unit's cases only (`set_grant` upserts one
   account's grant, so the 51 already set stay):
   `python -m scripts.load_client_size --from ~/osprey-load/b-1.0 --stages cases --grant intel:m10-cleared-unit-intel=viewer --grant nominals:m10-cleared-unit-records=viewer --grant companies:m10-cleared-unit-economic=viewer --grant transactions:m10-cleared-unit-economic=viewer --grant subscribers:m10-cleared-unit-comms=viewer --grant calls:m10-cleared-unit-comms=viewer --grant cells:m10-cleared-unit-comms=viewer --grant custody:m10-cleared-unit-custody=viewer --grant casefiles:m10-cleared-unit-investigations=viewer`
   (unit-fiu's, unit-covert's and unit-border's controls are already viewers of every case).
3. M10's leak and never-join files through `step4_stack.py`, as step 4's command list, at
   platform's head with `SUBJECTS` matching `counts.json`'s `subjects`.
4. Platform's `profile_m9.py`, read-only, on the database `ospreyflow`.
