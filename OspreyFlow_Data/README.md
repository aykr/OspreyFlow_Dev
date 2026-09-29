# OspreyFlow_Data

Datasets live here, one folder per dataset, and nothing in this folder is ever committed (git ignores
everything except this file). The product (`OspreyFlow_Core`) holds no data.

- `_local-runtime/` is the Conduit's local analytics store when it runs from a checkout.
- `basemap/` is the local basemap's source downloads and weights.
- A dataset you provision yourself, such as the real Enron corpus that ADR-053 allows on the owner's
  own machine only, gets its own folder here (`enron/`). Point `OSPREYFLOW_INTERNAL_DEMO_DATA_DIR` at
  this folder.

The packaging gate refuses any built artefact that contains a path under this folder
(`spec/06_DECISIONS.md` ADR-035 §C2 and ADR-054).
