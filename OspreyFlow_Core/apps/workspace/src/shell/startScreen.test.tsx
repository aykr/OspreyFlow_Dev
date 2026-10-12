// @vitest-environment jsdom
// ADR-115 decision 2 (E1): every surface outside a case shows the deployment's marking in the strip
// above its header — Start, Choose a case, the case to load into, the Admin area with no case.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StartChoice } from "./startScreen";
import { startScreen } from "./startScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function shown(choice: StartChoice) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));
  const element = startScreen({
    rights: new Set(["investigate", "edit_pipelines", "manage_people"]),
    rightsSettled: true,
    investigationId: null,
    startChoice: choice,
    setStartChoice: () => undefined,
    account: null,
    marking: "OFFICIAL-SENSITIVE",
    apiBaseUrl: "http://api",
    bearerToken: "t",
    lastCaseId: null,
    isAdministrator: false,
    openCase: () => undefined,
    browseCases: () => undefined,
    openStudio: () => undefined,
  });
  render(element!);
}

describe("the marking outside a case", () => {
  it.each([["start"], ["glass"], ["ingest"], ["admin"]] as const)("is shown on %s", (choice) => {
    shown(choice);
    expect(screen.getByRole("note", { name: "Protective marking" }).textContent).toBe("OFFICIAL-SENSITIVE");
  });
});
