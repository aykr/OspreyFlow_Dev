// @vitest-environment jsdom
//
// After *Set picture* succeeds the file control must be empty again. The input
// is uncontrolled, so clearing React's state alone left the browser showing the
// sent file's name — and, since its value was unchanged, choosing the same file
// again would not even fire `change` (found 9 October 2026).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { EntityPicture } from "./EntityPicture";

vi.mock("../canvas/entityPictures", () => ({
  entityPictureFor: () => undefined,
  onEntityPicturesChange: () => () => undefined,
  setEntityPicture: vi.fn(async () => []),
  removeEntityPicture: vi.fn(async () => ({})),
}));

vi.mock("../ingest/api", () => ({
  fetchHandlingScheme: async () => ({ classification: ["OFFICIAL"] }),
}));

afterEach(cleanup);

it("after Set picture succeeds, the file control no longer names the file sent", async () => {
  render(
    <EntityPicture
      nodeId="n1"
      types={new Set(["Device"])}
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="case-1"
      onDelta={() => undefined}
    />,
  );

  const input = screen.getByLabelText("Picture file") as HTMLInputElement;
  const file = new File(["png-bytes"], "mast.png", { type: "image/png" });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText("Picture legal basis"), {
    target: { value: "Operation Example" },
  });

  const set = screen.getByRole("button", { name: "Set picture" }) as HTMLButtonElement;
  await waitFor(() => expect(set.disabled).toBe(false));
  fireEvent.click(set);

  await waitFor(() => expect(set.disabled).toBe(true));
  // The control is remounted empty: re-query, since the sent-to node is gone.
  const after = screen.getByLabelText("Picture file") as HTMLInputElement;
  expect(after).not.toBe(input);
  expect(after.value).toBe("");
  expect(after.files?.length ?? 0).toBe(0);
});
