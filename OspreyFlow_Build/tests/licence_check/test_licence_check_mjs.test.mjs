// Deterministic proof that `tools/licence_check.mjs`'s own `isAllowed` predicate is sensitive
// to a real violation — the Node half of `make licence-check` had no test at all until this one
// (`06_DECISIONS.md` ADR-034 §B10's own gate audit found it), the same "prove it can fail"
// discipline `tests/licence_check/test_gpl_rejection.py` already applies to the Python half.

import { test } from "node:test";
import assert from "node:assert/strict";
import { isAllowed } from "../../tools/licence_check.mjs";

test("a GPL-3.0 licence is rejected", () => {
  assert.equal(isAllowed("GPL-3.0"), false);
});

test("a GNU General Public License, spelled out, is rejected", () => {
  assert.equal(isAllowed("GNU General Public License v3.0"), false);
});

test("an MIT licence is allowed", () => {
  assert.equal(isAllowed("MIT"), true);
});

test("an Apache-2.0 licence is allowed", () => {
  assert.equal(isAllowed("Apache-2.0"), true);
});

// Spec 00 §7: LGPL is not on the allowlist; it passes only for a package with a recorded exception
// (none among npm packages). This test used to assert the opposite.
test("LGPL-3.0 is refused for a package with no recorded exception", () => {
  assert.equal(isAllowed("LGPL-3.0", "some-package"), false);
  assert.equal(isAllowed("LGPL-3.0"), false);
});

// The review of 18 October 2026: the shape main() builds for a package naming two licences.
test("an LGPL term never carries an AGPL one through", () => {
  assert.equal(isAllowed("AGPL-3.0 AND LGPL-2.1"), false);
});

test("an OR is a choice, so one allowed alternative is enough, but AND needs every term", () => {
  assert.equal(isAllowed("Apache-2.0 OR GPL-3.0"), true);
  assert.equal(isAllowed("(MIT OR Apache-2.0) AND GPL-3.0"), false);
  assert.equal(isAllowed("GPL-3.0 OR AGPL-3.0"), false);
});

test("terms match by whole words, and CC-BY-SA is not CC-BY", () => {
  assert.equal(isAllowed("Limited Use"), false);
  assert.equal(isAllowed("CC-BY-SA-4.0"), false);
  assert.equal(isAllowed("CC-BY-4.0"), true);
});

test("the four licences added on 19 October 2026 pass", () => {
  for (const licence of ["0BSD", "Zlib", "CNRI-Python", "BSL-1.0"]) {
    assert.equal(isAllowed(licence), true, licence);
  }
});

test("a dual-licensed package naming both an allowed licence and GPL is rejected -- the real " +
  "shape main() produces via licenses.join(\" AND \"), where an allowed marker elsewhere in " +
  "the string must not let a GPL term slip through", () => {
  assert.equal(isAllowed("MIT AND GPL-3.0"), false);
});

// ADR-115 E1: the self-hosted typefaces (`@fontsource/*`) declare SIL OFL 1.1 by its SPDX short form,
// which spec 00's licence register allows ("SIL-OFL-1.1") and the long-name markers did not match.
test("an OFL-1.1 licence, by its SPDX short form, is allowed", () => {
  assert.equal(isAllowed("OFL-1.1"), true);
});

test("OFL-1.1 beside GPL is still rejected", () => {
  assert.equal(isAllowed("OFL-1.1 AND GPL-3.0"), false);
});
