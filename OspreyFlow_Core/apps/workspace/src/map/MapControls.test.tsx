// @vitest-environment jsdom
// The place search's words (`MapControls.tsx`), rule 2: an answer cut short is never told as "none".
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PlaceSearch } from "./MapControls";

async function ask(answer: { places: never[]; more: boolean }) {
  render(<PlaceSearch search={async () => answer} onGo={() => undefined} />);
  fireEvent.change(screen.getByRole("searchbox", { name: "Find a place" }), {
    target: { value: "cran" },
  });
  await act(async () => {
    fireEvent.submit(screen.getByRole("search", { name: "Find a place" }));
  });
  return screen.getByRole("status").textContent ?? "";
}

afterEach(cleanup);

describe("PlaceSearch", () => {
  it("says no place matched only when the answer was complete", async () => {
    expect(await ask({ places: [], more: false })).toContain(
      "No place called “cran” is in the gazetteer this case reads.",
    );
  });

  it("says more match when the store's first matches held no gazetteer place", async () => {
    const words = await ask({ places: [], more: true });
    expect(words).toContain("More places match “cran” than were looked through");
    expect(words).not.toContain("No place called");
  });
});
