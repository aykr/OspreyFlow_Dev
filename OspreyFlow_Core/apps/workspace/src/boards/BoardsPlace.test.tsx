// @vitest-environment jsdom
// The owner's navigation decision (ADR-145 Amendment 15): the strip's note left, so the drawing board's own screen says
// a board is a sketch that does not change the case's data, on an open board as on the list. What would fail if it
// were wrong: an open board drawn with no such line (the list's caption alone carried it before 0b5e031).
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { BoardsPlace } from "./BoardsPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("an open board says it is a sketch that does not change the case's data", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: "Not here." }), { status: 404 }));
  render(
    <BoardsPlace
      apiBaseUrl="http://conduit.test"
      bearerToken="t"
      caseId="k"
      caseName="Kestrel"
      selection={[]}
      entityTypes={[]}
      markings={["OFFICIAL"]}
      mayDraw
      initialBoard="b1"
    />,
  );
  expect(screen.queryByRole("heading", { name: /^Drawing boards in case/ })).toBeNull();
  expect(await screen.findByText("Drawing board: your sketch; it does not change the case's data.")).toBeTruthy();
});
