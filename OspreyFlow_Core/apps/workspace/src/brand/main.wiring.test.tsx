// @vitest-environment jsdom
//
// ADR-152 decision 14, invariant I9, at the one place that joins the links: `src/main.tsx` reads `/deployment.json`,
// takes `appearance.govukIdentity` from it, and hands it to `applyBrand` and `BrandFrame`. Each link has its own test
// (`readAppearance`, `applyBrand`, `BrandFrame`, `GovukHeader`); this runs the real entry point, with the fetch it
// meets stubbed to a deployment's file, and looks at what the page shows. The decision record names the failure this
// catches: the identity "keyed on the brand alone", here moved from the header into the entry point.
//
// The faults are planted at the shape `main.tsx` really has: a copy of its own text with one line changed, run the
// same way (`planted` below). Each must be seen to show the identity where the deployment's file says off (or hide it
// where the file says on), or the case that runs the real file proves nothing.
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../App", () => ({ App: () => <p>The Glass</p> }));

const SRC = join(__dirname, "..");
const MAIN = readFileSync(join(SRC, "main.tsx"), "utf-8");
const WIRING = "identityFromUrl(window.location.search, import.meta.env.DEV) ?? appearance.govukIdentity";

type Source = "real" | "constant true" | "brand alone" | "wrong key";

/** The text of `main.tsx` with its identity line replaced; refuses to plant if the line is not there. */
function plantedText(fault: Exclude<Source, "real">): string {
  expect(MAIN, "the line the plants replace has moved: update this test with it").toContain(WIRING);
  const replacement = {
    "constant true": "true",
    "brand alone": 'brand === "govuk"',
    "wrong key": "(appearance as unknown as Record<string, boolean | undefined>).govuk_identity ?? false",
  }[fault];
  return MAIN.replace(WIRING, replacement);
}

/** A copy of the entry point's text can live beside the tree, not in `src/` (so no test that walks it ever meets it) if its own
 * relative imports are made absolute: they resolve to the same modules, so `vi.mock("../App")` still applies. */
function withAbsoluteImports(text: string): string {
  return text.replace(/(from\s+|import\s+)"(\.{1,2}\/[^"]+)"/g, (_all, lead: string, spec: string) => {
    return `${lead}"${resolve(SRC, spec)}"`;
  });
}

interface Shown {
  identityMarker: string | null;
  logotype: boolean;
  headerText: string;
}

/** Runs the entry point (the real file, or a planted copy) against a deployment file, and reports what the page shows. */
async function runEntry(source: Source, appearance: Record<string, unknown>): Promise<Shown> {
  vi.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
  vi.stubGlobal("fetch", async () => ({
    ok: true,
    json: async () => ({ identity_provider: "https://id.example.test", realm: "osprey", appearance }),
  }));
  // jsdom loads no stylesheet, so the GOV.UK stylesheet's `load` never fires; answer it as a browser would.
  vi.spyOn(document.head, "append").mockImplementation((...nodes) => {
    for (const node of nodes) if (node instanceof HTMLLinkElement) node.onload?.(new Event("load"));
  });
  const folder = mkdtempSync(join(SRC, "..", ".main-wiring-"));
  try {
    if (source === "real") await import("../main");
    else {
      const copy = join(folder, "main.tsx");
      writeFileSync(copy, withAbsoluteImports(plantedText(source)));
      await import(/* @vite-ignore */ copy);
    }
    await waitFor(() => expect(document.getElementById("root")!.textContent).toContain("The Glass"));
  } finally {
    rmSync(folder, { recursive: true, force: true });
  }
  const root = document.getElementById("root")!;
  return {
    identityMarker: document.documentElement.getAttribute("data-govuk-identity"),
    logotype: root.querySelector(".govuk-header__logotype") !== null,
    headerText: root.querySelector(".govuk-header")?.textContent ?? "",
  };
}

const GOVUK = { brand: "govuk", service_name: "Prison Intelligence", organisation: "Ministry of Examples" };

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
  for (const name of ["data-brand", "data-govuk-identity", "data-govuk-typeface", "data-theme"]) {
    document.documentElement.removeAttribute(name);
  }
});

describe("the entry point's wiring of the GOV.UK identity switch", () => {
  it("shows the identity when the deployment's file says a real true", async () => {
    const shown = await runEntry("real", { ...GOVUK, govuk_identity: true });
    expect(shown.identityMarker).toBe("on");
    expect(shown.logotype).toBe(true);
  });

  // The deployment's file as a GOV.UK deployment can really send it: the key absent, false, and values that are not booleans.
  it.each([
    ["the key absent", {}],
    ["false", { govuk_identity: false }],
    ["the string true", { govuk_identity: "true" }],
    ["the string yes", { govuk_identity: "yes" }],
    ["the number 1", { govuk_identity: 1 }],
    ["null", { govuk_identity: null }],
  ])("shows no identity under the GOV.UK brand when the key is %s", async (_name, key) => {
    const shown = await runEntry("real", { ...GOVUK, ...key });
    expect(shown.identityMarker).toBeNull();
    expect(shown.logotype).toBe(false);
    expect(shown.headerText).toBe("Ministry of ExamplesPrison Intelligence");
  });

  it("shows no identity when the deployment sends no appearance at all", async () => {
    const shown = await runEntry("real", {});
    expect(shown.identityMarker).toBeNull();
    expect(shown.logotype).toBe(false);
  });

  it("means nothing under the OspreyFlow brand, switch or no switch", async () => {
    const shown = await runEntry("real", { brand: "ospreyflow", govuk_identity: true });
    expect(shown.identityMarker).toBeNull();
    expect(shown.logotype).toBe(false);
  });

  // Rule 15: each plant is the shape the entry point has, and each is seen red against the file the real one passes.
  describe("planted faults at the entry point are seen", () => {
    it("a constant true shows the identity on a deployment whose key is absent", async () => {
      const shown = await runEntry("constant true", GOVUK);
      expect(shown.identityMarker, "the plant must show the identity the file did not ask for").toBe("on");
      expect(shown.logotype).toBe(true);
    });

    it("a constant true shows it on a deployment whose key is not a boolean", async () => {
      const shown = await runEntry("constant true", { ...GOVUK, govuk_identity: "true" });
      expect(shown.identityMarker).toBe("on");
    });

    it("keying the identity on the brand alone shows it with the switch false", async () => {
      const shown = await runEntry("brand alone", { ...GOVUK, govuk_identity: false });
      expect(shown.identityMarker).toBe("on");
      expect(shown.logotype).toBe(true);
    });

    it("reading the wrong key hides the identity from a deployment that turned it on", async () => {
      const shown = await runEntry("wrong key", { ...GOVUK, govuk_identity: true });
      expect(shown.identityMarker).toBeNull();
      expect(shown.logotype).toBe(false);
    });
  });
});
