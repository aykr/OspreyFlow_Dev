// @vitest-environment jsdom
// ADR-113 stage 5: Export PDF — a refusal is said in words; a block that needs a justification names
// its items and asks for the two fields, and only then retries with both; a granted export prints.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExportControl } from "./ExportControl";
import { OFFICIAL_ITEM_FOR_EXPORT, json, manifest, serve } from "./reportsTestKit";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function place(print: (html: string) => void) {
  render(<ExportControl api={{ apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" }} packId="p1" print={print} />);
}

describe("Export PDF", () => {
  it("prints the manifest it is given", async () => {
    const calls = serve((c) => (c.path === "packs/p1/export" ? json(200, manifest([OFFICIAL_ITEM_FOR_EXPORT])) : null));
    const print = vi.fn();
    place(print);
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    await waitFor(() => expect(print).toHaveBeenCalledOnce());
    expect(String(print.mock.calls[0]?.[0])).toContain("Marked OFFICIAL");
    expect(calls[0]?.body).toEqual({});
  });

  it("names the blocked items and retries with a justification and an originator reference", async () => {
    let attempt = 0;
    const calls = serve((c) => {
      if (c.path !== "packs/p1/export") return null;
      attempt += 1;
      return attempt === 1
        ? json(422, { error: "override_required", detail: "x", blocked: [{ id: "n1", kind: "node", label: "Acme Ltd", reason: "consult_originator" }] })
        : json(200, manifest([OFFICIAL_ITEM_FOR_EXPORT]));
    });
    const print = vi.fn();
    place(print);
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    expect(await screen.findByText("Acme Ltd: consult originator")).toBeTruthy();
    const go = screen.getByRole("button", { name: "Export with override" }) as HTMLButtonElement;
    expect(go.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Justification"), { target: { value: "Board request" } });
    expect(go.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Originator reference"), { target: { value: "REF-7" } });
    fireEvent.click(go);
    await waitFor(() => expect(print).toHaveBeenCalledOnce());
    expect(calls[1]?.body).toEqual({ justification: "Board request", originator_reference: "REF-7" });
  });

  it("says a refusal in the server's words and prints nothing", async () => {
    serve(() => json(403, { error: "export_refused", detail: "Nothing in this pack is within your handling." }));
    const print = vi.fn();
    place(print);
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Nothing in this pack is within your handling.");
    expect(print).not.toHaveBeenCalled();
  });
});
