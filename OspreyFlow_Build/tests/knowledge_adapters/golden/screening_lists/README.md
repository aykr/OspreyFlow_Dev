# Screening-list golden files — synthetic (rule 9)

Every name, number and date in these files is invented. They are shaped exactly like each
publisher's documented export (see `OspreyFlow_Core/packages/knowledge_adapters/screening_lists.py`
for the documentation each format is read from, and which fields could not be verified from it).
No real OFAC, OFSI, UN, EU or OpenSanctions data is in this repository, in CI or in any test.
Countries are the ISO user-assigned codes XA, XB and XC, or invented names, so no real
jurisdiction is implied.

Each `<format>.*` input has a `<format>.expected.json` beside it: what the adapter must return.
