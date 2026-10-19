#!/usr/bin/env node
/**
 * `make licence-check` (Node half) — enforces the allowlist in
 * `spec/00_ARCHITECTURE.md` §7 against `license-checker`'s report.
 *
 * A licence is read as an expression, as the Python half reads it (its module docstring, and the
 * review of 18 October 2026): under OR one allowed alternative is enough; under AND, `;` and `,`
 * every term must be allowed; terms match by whole words; GPL and AGPL never pass; LGPL passes only
 * for a package named in RECORDED_LGPL_EXCEPTIONS. Before this, any text containing "lgpl" passed,
 * "AGPL-3.0 AND LGPL-2.1" with it.
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
  "cc-by-3.0",
  "cc-by-4.0",
  "blueoak",
  "unlicense",
  // Added 19 October 2026, the owner's choice (spec 00 §7): permissive, transitive only.
  "0bsd",
  "zlib",
  "cnri-python",
  "bsl-1.0",
  "boost software license",
];

/** spec/00_ARCHITECTURE.md §7's recorded LGPL exceptions among npm packages (none so far). */
export const RECORDED_LGPL_EXCEPTIONS = new Set([]);

const OPERATOR = /(\(|\)|;|,|\band\b|\bor\b)/;
const LGPL = /(?<![a-z])lgpl|lesser general public|library general public/;
const GPL = /(?<![a-z])a?gpl|general public licen[cs]e|affero/;
const MARKERS = ALLOWED_MARKERS.map(
  (m) => new RegExp(`(?<![a-z0-9])${m.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![a-z0-9])`),
);

function termAllowed(term, pkg) {
  if (LGPL.test(term)) return pkg !== undefined && RECORDED_LGPL_EXCEPTIONS.has(pkg.toLowerCase());
  if (GPL.test(term)) return false;
  return MARKERS.some((marker) => marker.test(term));
}

function tokens(licenseText) {
  let text = String(licenseText).toLowerCase().replace("library or lesser", "lesser");
  // A parenthesised aside with no operator in it is part of the licence's name, not a group.
  text = text.replace(/\(([^()]*)\)/g, (whole, inner) => (OPERATOR.test(inner) ? whole : ` ${inner} `));
  return text.split(OPERATOR).map((t) => t.trim()).filter((t) => t.length > 0);
}

/** The whole expression allowed; `pkg` names an LGPL exception, if any. Unparseable: refused. */
export function isAllowed(licenseText, pkg) {
  const list = tokens(licenseText);
  let position = 0;
  const peek = () => list[position];
  const take = () => list[position++];
  const atom = () => {
    const token = peek();
    if (token === undefined || ["and", "or", ";", ",", ")"].includes(token)) throw new Error("licence expected");
    take();
    if (token === "(") {
      const inner = either();
      if (peek() !== ")") throw new Error("unbalanced parenthesis");
      take();
      return inner;
    }
    return termAllowed(token, pkg);
  };
  const both = () => {
    let result = atom();
    while (["and", ";", ","].includes(peek())) {
      take();
      result = atom() && result;
    }
    return result;
  };
  const either = () => {
    let result = both();
    while (peek() === "or") {
      take();
      result = both() || result;
    }
    return result;
  };
  try {
    const result = either();
    return result && position === list.length;
  } catch {
    return false;
  }
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
    const name = key.slice(0, key.lastIndexOf("@")) || key;
    if (!isAllowed(licenses, name)) {
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
