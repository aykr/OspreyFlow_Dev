// @vitest-environment jsdom
// ADR-099 Amendment 9: a timeline with no events, in a case whose datasets' events another case holds,
// says where they are instead of claiming the data carries no dates; with no holder it says what it
// always said.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("echarts/core", () => ({
  use: () => undefined,
  init: () => ({ setOption: () => undefined, on: () => undefined, off: () => undefined, dispatchAction: () => undefined,
    resize: () => undefined, dispose: () => undefined, getOption: () => ({}) }),
}));  // prettier-ignore
const holders = vi.fn();
vi.mock("../analytics/api", () => ({
  fetchHistogram: async () => ({ bucketing: "fixed_interval", buckets: [], total: 0 }),
  fetchCaseEvents: (...args: unknown[]) => holders(...args),
}));

import { createCrossFilterStore } from "../crossfilter/store";
import { Timeline } from "./Timeline";

afterEach(cleanup);

function place() {
  render(
    <Timeline apiBaseUrl="http://test.invalid" bearerToken="t" investigationScope="review"
      crossFilterStore={createCrossFilterStore("http://test.invalid", "t", "review")} getNodeIds={() => []} />,
  );  // prettier-ignore
}

describe("an empty timeline", () => {
  it("says which case holds its datasets' events", async () => {
    holders.mockResolvedValue({ has_events: false, held_by: [{ investigation_id: "l1", name: "Operation Ledger (synthetic demo)" }] });
    place();
    expect(await screen.findByText(/The events of the datasets it reads are in Operation Ledger \(synthetic demo\)\./)).toBeTruthy();
    expect(holders).toHaveBeenCalledWith("http://test.invalid", "t", "review");
    expect(screen.queryByText(/does not carry/)).toBeNull();
  });

  it("says what it always said when no case the reader can open holds them", async () => {
    holders.mockResolvedValue({ has_events: false, held_by: [] });
    place();
    expect(await screen.findByText(/which this case.s data does not carry/)).toBeTruthy();
  });
});
