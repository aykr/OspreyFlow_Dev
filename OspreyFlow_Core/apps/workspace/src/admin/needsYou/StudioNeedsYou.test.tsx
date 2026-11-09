// @vitest-environment jsdom
// The Studio's side of *Needs you* (ADR-145 decision 11, A2; ADR-090 Amendment 4; L2.7): the Model tab
// reads *1 Model · n proposed* with the count the Conduit made for this reader in this dataset alone,
// a reminder with its tip shows above the other tabs, and *Needs you* opens the Model tab. The count
// leaving out what the reader cannot read is the Conduit's (`test_needs_you.py`); here, that the tab
// shows that count and no other (another dataset's, or one above the reader's clearance).
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IngestStudio } from "../../ingest/IngestStudio";
import { NEEDS_YOU_WORDS } from "./needsYouApi";
import { requestOpening } from "./openings";

vi.mock("../../ingest/map/MapScreen", () => ({ MapScreen: () => null }));
vi.mock("../../ingest/verify/VerifyScreen", () => ({
  VerifyScreen: () => null,
}));
vi.mock("../../ingest/publish/PublishScreen", () => ({
  PublishScreen: () => null,
}));
vi.mock("../../ingest/ProfileScreen", () => ({ ProfileScreen: () => null }));
vi.mock("../../ingest/ConnectScreen", () => ({ ConnectScreen: () => null }));
vi.mock("../../ingest/dag/NodePreview", () => ({ NodePreview: () => null }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

const CASES = [
  { id: "inv-1", name: "PID case", level: "editor", created_at: "", created_by: "e",
    datasets: ["Prison records"], dataset_ids: ["ds-a"] },
]; // prettier-ignore

function serve(
  proposals: {
    dataset_id: string;
    dataset_name: string;
    to_decide: number;
    above_clearance: boolean;
  }[],
) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = String(url);
      asked.push(path);
      const json = (payload: unknown) =>
        ({ ok: true, status: 200, json: async () => payload }) as Response;
      if (path.endsWith("/v1/me/needs-you"))
        return json({ promotions_overdue: [], proposals });
      if (path.endsWith("/v1/investigations")) return json(CASES);
      if (path.endsWith("/screening-subscriptions"))
        return json({ lists: [], subscribed: [] });
      if (path.endsWith("/model/proposals")) return json({ proposals: [] });
      return json([]);
    }),
  );
  return asked;
}

const open = () =>
  render(
    <IngestStudio
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="inv-1"
      onOpenCase={vi.fn()}
    />,
  );

describe("the Studio's proposals count", () => {
  it("names this dataset's count on the Model tab, never another's or one above the reader's clearance", async () => {
    serve([
      {
        dataset_id: "ds-a",
        dataset_name: "Prison records",
        to_decide: 2,
        above_clearance: true,
      },
      {
        dataset_id: "ds-b",
        dataset_name: "Other",
        to_decide: 7,
        above_clearance: false,
      },
    ]);
    open();
    expect(
      await screen.findByRole("tab", { name: "1 Model · 2 proposed" }),
    ).toBeTruthy();
  });

  it("shows the reminder with its tip above the other tabs, and it opens the Model tab", async () => {
    serve([
      {
        dataset_id: "ds-a",
        dataset_name: "Prison records",
        to_decide: 1,
        above_clearance: false,
      },
    ]);
    open();
    const reminder = await screen.findByRole("button", {
      name: NEEDS_YOU_WORDS.reminder(1),
    });
    expect(
      document.getElementById(reminder.getAttribute("aria-describedby")!)
        ?.textContent,
    ).toBe(NEEDS_YOU_WORDS.reminderTip);
    fireEvent.click(reminder);
    await waitFor(() =>
      expect(
        screen
          .getByRole("tab", { name: "1 Model · 1 proposed" })
          .getAttribute("aria-selected"),
      ).toBe("true"),
    );
    expect(
      screen.queryByRole("button", { name: NEEDS_YOU_WORDS.reminder(1) }),
    ).toBeNull();
  });

  it("draws no count and no reminder when nothing is to decide here", async () => {
    const asked = serve([
      {
        dataset_id: "ds-a",
        dataset_name: "Prison records",
        to_decide: 0,
        above_clearance: true,
      },
    ]);
    open();
    await waitFor(() =>
      expect(asked.some((p) => p.endsWith("/v1/me/needs-you"))).toBe(true),
    );
    expect(screen.getByRole("tab", { name: "1 Model" })).toBeTruthy();
    expect(screen.queryByText(/wait.? for you on the Model tab/)).toBeNull();
  });

  it("opens on the Model tab when Needs you asked for this dataset", async () => {
    serve([
      {
        dataset_id: "ds-a",
        dataset_name: "Prison records",
        to_decide: 1,
        above_clearance: false,
      },
    ]);
    requestOpening({ kind: "studio", tab: "model", datasetId: "ds-a" });
    open();
    await waitFor(() =>
      expect(
        screen
          .getByRole("tab", { name: /^1 Model/ })
          .getAttribute("aria-selected"),
      ).toBe("true"),
    );
  });
});
