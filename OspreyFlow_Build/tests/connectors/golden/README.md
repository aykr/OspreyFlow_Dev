# Screening templates' golden files: synthetic (rule 9)

Each format template reads the synthetic input already kept for its adapter in
`../knowledge_adapters/golden/screening_lists/` (invented names, numbers and dates, shaped like each
publisher's documented export), and `<template>.screening.json` here is the one screening shape it must
give: primary name, aliases, date of birth, nationality, identifiers, programme, listing, entity type,
keyed on the publisher's reference (`06_DECISIONS.md` ADR-140 Amendment 9 decision 3; Amendment 13).

`blank_client_list.csv` is an invented client's own list, in no publisher's format, mapped by
`blank_client_list.mapping.json` (column picks only, rule 8). Countries are the ISO user-assigned codes
XA, XB and XC. No real sanctions list is in this repository, in CI or in any test.
