// @vitest-environment jsdom
// Admin › Models' usage and limits (ADR-135 Amendment 3): the limits form sends whole numbers and
// refuses a half-set budget before any call; the usage table shows the Conduit's counts for the
// period asked, and a new period asks again.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Models } from "../admin/sections/Models";
import { ModelsUsage, limitsInWords } from "./ModelsUsage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const GEMINI = { name: "gemini", label: "Gemini", roles: { extraction: "gemini-2.5-flash" }, api_base: null, privacy_contract: false, contract_reference: null };
const NONE = { requests_per_minute: null, tokens_per_minute: null, budget_tokens: null, budget_period: null };
const VIEW = {
  engines: [{ provider: GEMINI, key_state: "set", key_set_at: null, key_set_by: null, default_for: [], limits: NONE }],
  defaults: {},
  local_models: { extraction: "qwen2.5:7b-instruct", vision: null, transcription: null, embedding: null },
  local_only: false,
  sendable_handling_codes: ["O"],
  source: "models file",
};
const FIG = (calls: number, tokens: number) => ({ calls, succeeded: calls, failed: 0, prompt_tokens: tokens, completion_tokens: 0, tokens });
const USAGE = {
  start: "2026-10-10",
  end: "2026-11-08",
  rows: [{ engine: "gemini", engine_label: "Gemini", job: "extraction", figures: FIG(12, 3400) }],
  by_engine: { gemini: FIG(12, 3400) },
  by_job: { extraction: FIG(12, 3400) },
  total: FIG(12, 3400),
};

function stub() {
  const sent: { url: string; method: string; body: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = new URL(String(url));
      sent.push({ url: u.pathname + u.search, method: init?.method ?? "GET", body: String(init?.body ?? "") });
      const body =
        u.pathname === "/v1/admin/models/history"
          ? { entries: [] }
          : u.pathname === "/v1/admin/models/usage"
            ? USAGE
            : u.pathname.endsWith("/limits")
              ? { ...VIEW, engines: [{ ...VIEW.engines[0], limits: JSON.parse(String(init?.body)).limits }] }
              : VIEW;
      return { ok: true, status: 200, json: async () => body } as Response;
    }),
  );
  return sent;
}

const API = { apiBaseUrl: "http://api", bearerToken: "t" };

describe("limits", () => {
  it("sends whole numbers, blank as no limit, and shows the limits in words", async () => {
    const sent = stub();
    render(<Models api={API} />);
    fireEvent.click(await screen.findByRole("button", { name: "Set limits for Gemini" }));
    fireEvent.change(screen.getByLabelText("Requests a minute"), { target: { value: "60" } });
    fireEvent.change(screen.getByLabelText(/Token budget/), { target: { value: "1,000,000" } });
    fireEvent.change(screen.getByLabelText("Budget period"), { target: { value: "month" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the limits" }));
    await screen.findByText(/its limits are saved/);
    const put = sent.find((s) => s.method === "PUT");
    expect(put?.url).toBe("/v1/admin/models/engines/gemini/limits");
    expect(JSON.parse(put!.body)).toEqual({
      limits: { requests_per_minute: 60, tokens_per_minute: null, budget_tokens: 1000000, budget_period: "month" },
    });
    expect(screen.getByRole("table", { name: "Engines" }).textContent).toContain("60 requests a minute; 1,000,000 tokens a month");
  });

  it("refuses a budget without its period before asking the Conduit", async () => {
    const sent = stub();
    render(<Models api={API} />);
    fireEvent.click(await screen.findByRole("button", { name: "Set limits for Gemini" }));
    fireEvent.change(screen.getByLabelText(/Token budget/), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the limits" }));
    expect((await screen.findByRole("alert")).textContent).toContain("A budget needs both its tokens and its period");
    expect(sent.filter((s) => s.method === "PUT")).toEqual([]);
  });

  it("says no limits where none is set", () => {
    expect(limitsInWords(NONE)).toBe("No limits");
    expect(limitsInWords({ ...NONE, tokens_per_minute: 2000 })).toBe("2,000 tokens a minute");
  });
});

describe("usage", () => {
  it("shows the gateway's counts for the last 30 days, and asks again for a new period", async () => {
    const sent = stub();
    render(<ModelsUsage api={API} today={new Date("2026-11-08T12:00:00Z")} />);
    const table = await screen.findByRole("table", { name: "Usage by engine and job" });
    expect(within(table).getByText("Extraction and Ask")).toBeTruthy();
    expect(table.textContent).toContain("3,400");
    expect(sent[0]?.url).toBe("/v1/admin/models/usage?start=2026-10-10&end=2026-11-08");
    fireEvent.change(screen.getByLabelText("Period"), { target: { value: "month" } });
    await waitFor(() => expect(sent.at(-1)?.url).toBe("/v1/admin/models/usage?start=2026-11-01&end=2026-11-08"));
    fireEvent.change(screen.getByLabelText("Period"), { target: { value: "chosen" } });
    fireEvent.change(screen.getByLabelText("First day"), { target: { value: "2026-11-02" } });
    fireEvent.change(screen.getByLabelText("Last day"), { target: { value: "2026-11-03" } });
    fireEvent.click(screen.getByRole("button", { name: "Show the usage" }));
    await waitFor(() => expect(sent.at(-1)?.url).toBe("/v1/admin/models/usage?start=2026-11-02&end=2026-11-03"));
  });
});
