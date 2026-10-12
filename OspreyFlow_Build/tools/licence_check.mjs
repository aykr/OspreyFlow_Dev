#!/usr/bin/env node
/**
 * `make licence-check` (Node half) — enforces the allowlist in
 * `spec/00_ARCHITECTURE.md` §7 against `license-checker`'s report.
 *
 * Known gap, accepted and flagged rather than fixed here (Phase 0 plan §2.D,
 * same reasoning as the Python-side script): linkage mode for LGPL-3.0 is not
 * checked.
 *
 * Also allows CC0-1.0, CC-BY-3.0/4.0, Python-2.0 (PSF) and BlueOak-1.0.0,
 * none of which are itemised in `00_ARCHITECTURE.md` §7 but are all
 * permissive/OSI-approved and are unavoidable transitive licences in the
 * npm ecosystem (data/font packages such as caniuse-lite; BlueOak-1.0.0
 * arrived via `minimatch`@10+ and its own transitive dependents once Phase
 * 4 added Vite/Vitest/typescript-eslint). Noted rather than silently
 * absorbed: flag to the spec owner as missing allowlist entries, same as
 * the PSF-2.0 case on the Python side.
 */

import { execFileSync } from "node:child_process";

const ALLOWED_MARKERS = [
  "mit",
  "apache",
  "bsd",
  "isc",
  "mozilla public license",
  "mpl-2.0",
  "sil open font",
  "open font license",
  "ofl-1.1",
  "psf",
  "python-2.0",
  "python software foundation",
  "cc0",
  "cc-by",
  "blueoak",
];

export function isAllowed(licenseText) {
  const text = String(licenseText).toLowerCase();
  if (text.includes("lesser general public license") || text.includes("lgpl")) {
    return true; // LGPL-3.0, dynamic linking only — linkage not checked, see file docstring.
  }
  if (text.includes("general public license") || text.includes("gpl")) {
    return false;
  }
  return ALLOWED_MARKERS.some((marker) => text.includes(marker));
}

function runLicenseChecker() {
  const output = execFileSync(
    "npx",
    ["--yes", "license-checker", "--json"],
    { encoding: "utf8" },
  );
  return JSON.parse(output);
}

function main() {
  const report = runLicenseChecker();
  const offenders = [];
  for (const [key, info] of Object.entries(report)) {
    if (info.private) continue; // this repo's own root package, not a dependency
    const licenses = Array.isArray(info.licenses) ? info.licenses.join(" AND ") : info.licenses;
    if (!isAllowed(licenses)) {
      offenders.push({ key, licenses });
    }
  }

  for (const offender of offenders) {
    console.error(
      `licence-check: ${offender.key} — '${offender.licenses}' is not on the ` +
        "spec/00_ARCHITECTURE.md §7 allowlist",
    );
  }
  if (offenders.length > 0) {
    process.exit(1);
  }
  console.log(`licence-check: ${Object.keys(report).length} packages, all allowed.`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
