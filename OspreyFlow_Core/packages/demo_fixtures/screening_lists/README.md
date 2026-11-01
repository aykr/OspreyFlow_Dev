# Synthetic screening lists (rule 9)

Invented entries, shaped like OpenSanctions' `entities.ftm.json` (one FollowTheMoney entity per
line), for the Lists screen, re-screening demonstrations and tests. No real OFAC, OFSI, UN, EU or
OpenSanctions data is held anywhere in this repository.

- `synthetic_opensanctions_v1.ftm.json` — the ten names of `../screening_list_synthetic.yaml`.
- `synthetic_opensanctions_v2.ftm.json` — the next version: one entry added (Tomas ZELINSKY, who
  matches an Operation Ledger customer), one changed (a date of birth given), one removed.

`synthetic.sha256` lists each file's SHA-256. A subscription's refresh treats a list as synthetic
only when every file it reads is listed there (`services/api/screening_refresh.py`); any other file
is real data and needs this device's `real_data_exceptions.yaml` to name its dataset. Change a file
here and its digest must be updated, or the refresh refuses it as real.
