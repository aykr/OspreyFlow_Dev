# Synthetic screening lists (rule 9)

Invented entries, shaped like OpenSanctions' `entities.ftm.json` (one FollowTheMoney entity per
line) or the FCDO's `UK-Sanctions-List.xml`, for the Lists screen, re-screening demonstrations and
tests. No real OFAC, OFSI, UN, EU, OpenSanctions or UK Sanctions List data is held anywhere in this
repository.

- `synthetic_opensanctions_v1.ftm.json` — the ten names of `../screening_list_synthetic.yaml`.
- `synthetic_opensanctions_v2.ftm.json` — the next version: one entry added (Tomas ZELINSKY, who
  matches an Operation Ledger customer), one changed (a date of birth given), one removed.

- `synthetic_uk_sanctions_list_v1.xml` — an invented UK Sanctions List (FCDO format; ADR-133
  Amendment 6): four people and organisations and one ship, none of them an Operation Ledger
  customer. Operation Ledger's demo subscribes to it (ADR-108 Amendment 5, use case A3).
- `synthetic_uk_sanctions_list_v2.xml` — its next version: one designation added (Sofia RUIZ, born
  14 June 2001, who is an Operation Ledger customer), one changed (a spelling variation given), one
  removed. Re-screening against it raises exactly one alert in the Ledger case.

`synthetic.sha256` lists each file's SHA-256. A subscription's refresh treats a list as synthetic
only when every file it reads is listed there (`services/api/screening_refresh.py`); any other file
is real data and needs this device's `real_data_exceptions.yaml` to name its dataset. Change a file
here and its digest must be updated, or the refresh refuses it as real.
