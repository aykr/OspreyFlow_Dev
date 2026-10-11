// @vitest-environment jsdom
// ADR-113 stage 5: the trend builder offers only what `/trends/options` returns, previews and saves
// what the form says, draws every period and series, says a refused trend in words with its three
// choices, and puts a saved trend into a pack.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PACK, OPTIONS, figures, json, serve, type Call } from "./reportsTestKit";
import { TrendsTab } from "./TrendsTab";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SAVED = { id: "t1", investigation_id: "c1", created_by: "ana", created_at: "2026-10-01T09:00:00Z", updated_at: "2026-10-01T09:00:00Z", ...figures().definition };

function routes(extra: (call: Call) => Response | null = () => null, saved: unknown[] = []) {
  return (call: Call) =>
    extra(call) ??
    (call.method === "GET" && call.path === "trends/options" ? json(200, OPTIONS)
      : call.method === "GET" && call.path === "trends" ? json(200, saved)
      : call.method === "GET" && call.path === "packs" ? json(200, [PACK])
      : call.method === "GET" && call.path === "trends/t1/figures" ? json(200, figures())
      : null);  // prettier-ignore
}

function place(canAssemble = true) {
  render(<TrendsTab api={{ apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" }} canAssemble={canAssemble} />);
}

async function build() {
  fireEvent.change(await screen.findByLabelText("Title"), { target: { value: "Payments by channel" } });
  fireEvent.click(await screen.findByLabelText("Payments"));
}

describe("the trend builder", () => {
  it("offers only the options' event types, and only fields every chosen type declares", async () => {
    serve(routes());
    place();
    await screen.findByLabelText("Payments");
    expect(screen.getAllByRole("checkbox").map((c) => c.parentElement?.textContent)).toEqual(["Payments", "Transfers", "Logins"]);
    expect(screen.queryByRole("textbox", { name: /event type/i })).toBeNull();

    fireEvent.click(screen.getByLabelText("Payments"));
    fireEvent.click(screen.getByLabelText("Transfers"));
    fireEvent.click(screen.getByLabelText("Sum"));
    const sum = screen.getByLabelText("Property to add up") as HTMLSelectElement;
    // "fee" is declared by Transfers only, so a sum over both cannot use it.
    expect([...sum.options].map((o) => o.value)).toEqual(["", "amount"]);
    const series = screen.getByLabelText("Series") as HTMLSelectElement;
    expect([...series.options].map((o) => o.value)).toEqual(["", "event_type", "channel"]);

    // Adding a type that shares no number field leaves nothing to sum and drops a chosen one.
    fireEvent.change(sum, { target: { value: "amount" } });
    fireEvent.click(screen.getByLabelText("Logins"));
    expect([...(screen.getByLabelText("Property to add up") as HTMLSelectElement).options].map((o) => o.value)).toEqual([""]);
    expect((screen.getByLabelText("Property to add up") as HTMLSelectElement).value).toBe("");
  });

  it("previews the definition the form says and draws one bar per period and every series", async () => {
    const calls = serve(routes((c) => (c.method === "POST" && c.path === "trends/preview" ? json(200, figures()) : null)));
    place();
    await build();
    fireEvent.click(screen.getByLabelText("Sum"));
    fireEvent.change(screen.getByLabelText("Property to add up"), { target: { value: "amount" } });
    fireEvent.change(screen.getByLabelText("Weeks back"), { target: { value: "26" } });
    fireEvent.change(screen.getByLabelText("Series"), { target: { value: "channel" } });
    fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
    fireEvent.change(screen.getByLabelText("Filter property"), { target: { value: "channel" } });
    fireEvent.change(screen.getByLabelText("Filter value"), { target: { value: "card" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    const chart = await screen.findByRole("img", { name: /Payments by channel/ });
    expect(calls.find((c) => c.path === "trends/preview")?.body).toEqual({
      title: "Payments by channel", event_types: ["payment"], measure: "sum", measure_field: "amount",
      interval: "week", weeks: 26, group_by: "channel", filters: [{ field: "channel", value: "card" }],
    });  // prettier-ignore
    expect(chart.querySelectorAll("[data-period]")).toHaveLength(3);
    const legend = screen.getByRole("list", { name: "Series legend" });
    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["card", "wire"]);
    expect(screen.getByText("Marked OFFICIAL")).toBeTruthy();
    expect(screen.getByText("Sum of amount: 12,400 over 31 events in 12 weeks; 2 events had no amount and are not in the sum")).toBeTruthy();
  });

  it("says a trend past its limit in words, with its three choices", async () => {
    serve(routes((c) => (c.path === "trends/preview" ? json(409, { error: "limit_exceeded", cap_kind: "periods", cap: 60, would_be: 104, options: ["shorter_period", "monthly_interval", "fewer_series"] }) : null)));
    place();
    await build();
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "This trend would have 104 periods, past its limit of 60. Choose a shorter period, a monthly interval, or fewer series.",
    );
  });

  it("says a refused definition in the server's words", async () => {
    serve(routes((c) => (c.path === "trends/preview" ? json(422, { error: "trend_refused", detail: "payment declares no field called fee" }) : null)));
    place();
    await build();
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect((await screen.findByRole("alert")).textContent).toBe("payment declares no field called fee");
  });

  it("saves the definition and refreshes the saved list, choosing the new trend", async () => {
    let saved: unknown[] = [];
    const calls = serve(
      routes((c) => {
        if (c.method === "POST" && c.path === "trends") {
          saved = [SAVED];
          return json(201, SAVED);
        }
        return c.method === "GET" && c.path === "trends" ? json(200, saved) : null;
      }),
    );
    place();
    await build();
    expect(screen.queryByRole("button", { name: "Payments by channel" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save trend" }));
    expect(await screen.findByRole("button", { name: "Payments by channel" })).toBeTruthy();
    expect(calls.find((c) => c.method === "POST" && c.path === "trends")?.body).toMatchObject({ title: "Payments by channel", event_types: ["payment"], measure: "count", measure_field: null, group_by: null, filters: [] });
    expect(calls.filter((c) => c.method === "GET" && c.path === "trends")).toHaveLength(2);
    expect(await screen.findByRole("img", { name: /Payments by channel/ })).toBeTruthy();
  });

  it("will not preview or save without a title, an event type and a sum's property", async () => {
    const calls = serve(routes());
    place();
    await screen.findByLabelText("Payments");
    expect((screen.getByRole("button", { name: "Preview" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Give the trend a title.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "x" } });
    fireEvent.click(screen.getByLabelText("Payments"));
    fireEvent.click(screen.getByLabelText("Sum"));
    expect(screen.getByText("Choose the property to add up.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save trend" }));
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("offers at most five filters", async () => {
    serve(routes());
    place();
    await build();
    for (let i = 0; i < 5; i++) fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
    expect(screen.getAllByLabelText("Filter property")).toHaveLength(5);
    expect((screen.getByRole("button", { name: "Add filter" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("a saved trend", () => {
  it("is drawn when chosen and added to a pack", async () => {
    const calls = serve(routes((c) => (c.method === "POST" && c.path === "packs/p1/items" ? json(201, { id: "i9" }) : null), [SAVED]));
    place();
    fireEvent.click(await screen.findByRole("button", { name: "Payments by channel" }));
    expect(await screen.findByRole("img", { name: /Payments by channel/ })).toBeTruthy();
    await waitFor(() => expect((screen.getByLabelText("Pack") as HTMLSelectElement).value).toBe("p1"));
    fireEvent.click(screen.getByRole("button", { name: "Add to pack" }));
    expect(await screen.findByText("Added to Quarter pack")).toBeTruthy();
    expect(calls.find((c) => c.path === "packs/p1/items")?.body).toEqual({ kind: "trend", trend_id: "t1" });
  });

  it("is not offered to a pack to someone who may not assemble one", async () => {
    const calls = serve(routes(() => null, [SAVED]));
    place(false);
    fireEvent.click(await screen.findByRole("button", { name: "Payments by channel" }));
    await screen.findByRole("img", { name: /Payments by channel/ });
    expect(screen.queryByRole("button", { name: "Add to pack" })).toBeNull();
    expect(screen.queryByLabelText("Pack")).toBeNull();
    // Nor does it ask for the case's packs: a route it would only be refused.
    expect(calls.some((c) => c.path === "packs")).toBe(false);
  });

  it("is deleted", async () => {
    const calls = serve(routes((c) => (c.method === "DELETE" ? json(204, null) : null), [SAVED]));
    place();
    fireEvent.click(await screen.findByRole("button", { name: "Payments by channel" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "trends/t1")).toBe(true));
  });
});
