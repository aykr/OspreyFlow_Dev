# Slice PL6 · PL6 · The `pages` image scan: no React in the built image (ADR-152 Amendment 1, I23)

- **Build id:** PL6
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing (PL3, the `pages` image, is on main)
- **Status of this brief:** written by the conductor on 20 November 2026 on the owner's word of the same day ("PL6: cut and start it:
  the scan script, its test with the three planted faults, no edit to the Makefile or ci.yml; those are diffs for me"), from the
  owner's accepted ADR-152 Amendment 1 and its impact note. **Amendment 1 is accepted but not yet committed** (the owner commits it
  after GG6 merges); read it from the owner's folder, read-only, and do not copy it into the repository or cite it in committed text:
  `/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform/ospreyflow/Claude outputs/ospreyflow_clean_govuk_install_2026-11-20/`
  (`ADR-152_amendment.diff` for I23's wording, `IMPACT_ON_BUILD.md` section "PL6", `evidence/E1_pages_runtime_install_measured.txt` and
  `E2_planted_fault_and_no_workspace_install.txt` for what was measured, and `PL6_Makefile.diff` / `PL6_ci.yml.diff` to see the
  wiring that is the owner's).

## What

Invariant I23: the built `pages` image (`OspreyFlow_Core/apps/pages/Dockerfile`) carries no React. This slice writes the scan and its
test. **It does not wire the scan**: `OspreyFlow_Core/Makefile` and `.github/workflows/ci.yml` are protected and the owner applies the
diffs himself, once the scan has been shown red (rule 15). Do not edit either file, and do not edit the Dockerfile.

1. **The scan** `OspreyFlow_Core/scripts/pages_image_react_scan.py`, run as `python -m scripts.pages_image_react_scan --image <tag>
   --sbom <file>` (the form `PL6_Makefile.diff` uses). It reads (a) the CycloneDX SBOM that `trivy image --format cyclonedx` writes
   and (b) the image's exported file system (`docker create` then `docker export`, extracted to a temporary folder it removes). It
   fails, naming the finding and never printing a secret, on: a component named `react`, `react-dom` or `scheduler` in the SBOM; the
   strings `react/jsx-runtime` or `react/jsx-dev-runtime`, or React's element markers (the `$$typeof` symbol `react.element`,
   `Symbol.for("react.` and `react.transitional.element`), in any file under `/app`; and it fails **unless the SBOM names `express`
   and `nunjucks`** (an empty or wrong SBOM must not pass). Separate the pure part from the Docker part: pure functions that take an
   SBOM document and a folder, and a thin `main` that does the `docker` calls. The pure functions are what the test drives.
2. **Its test** `OspreyFlow_Build/tests/glass_trees/test_pages_image_carries_no_react.py` (the folder does not exist on main yet:
   create it with an `__init__.py` if the neighbouring test folders have one). Pure: no Docker, no network. A synthetic CycloneDX
   SBOM and a synthetic exported tree under `tmp_path`, in the shape `trivy` and `docker export` really produce (read the evidence
   files for the shape; generate nothing that looks like a secret). **Three planted faults, each shown red against the real call
   site, and the clean case green:**
   - the run-time stage's install without the workspace flag: take the **real** `apps/pages/Dockerfile` text, remove
     `--workspace apps/pages` from the `runtime-deps` stage's `npm ci --omit=dev`, and assert the test's own check of that stage
     (the Dockerfile's run-time install names the pages workspace alone) goes red; the evidence says the unscoped install brings in
     all three packages, and the SBOM it would give is the second half of this plant;
   - a bundle holding `react/jsx-runtime` under the exported `/app`: red;
   - an empty SBOM (and an SBOM without `express` or `nunjucks`): red;
   - and the clean SBOM plus a clean tree: green, with `express` and `nunjucks` present (control). Also a near-miss that must **not**
     fail: a package called `react-dom-like` or a file that says "reaction" (the scan matches names, not substrings).
   State, in the file's header, which test fails if the run-time install loses its scope (rule 12).
3. **Hand-over for the owner, in your report:** the wiring is the owner's diffs; say whether they still apply to main
   (`git apply --check` on both from the repository root, read-only) and whether `PL6_Makefile.diff`'s command line matches your
   script's arguments. Do not apply them.

Binding: process/CLAUDE.md rules 8 (the scan owed since PL3 is the owner's wiring), 12, 15; British English; no real data, no secret;
the client's name only in the four keep-files.

## Acceptance test

The new file alone. Red on main because neither the script nor the folder exists.

## Checks

Pure only. The **checks command** runs `tests/harness/test_dockerfiles_numeric_user.py`, `tests/harness/test_service_inventory.py`
and `tests/test_doc_citations_check.py`-style neighbours the line names for the folders you touch (it adds every mapped pure test that
scans `OspreyFlow_Core/scripts/` or `OspreyFlow_Build/tests/`). A new pure test needs a row in the scan map only if it walks a
folder; this one should read the Dockerfile by name and walk only its own `tmp_path`: say so in your report with the reason, so the
conductor can record the row (the map is the line's file; you cannot edit it).

## Out of scope

The Makefile and `ci.yml` wiring (the owner's diffs); `PL7`'s renderer and release diff; I22, I24 and I25; any change to the `pages`
Dockerfile or to `apps/pages`; the live image build (the merge lock was present when the evidence was gathered; the scan on a real
image is the owner's first run after wiring: list it as owed).
