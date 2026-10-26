// @vitest-environment jsdom
// ADR-128 decision 3: an attachment of the case brief that is a saved trend opens the Reports view on
// its Trends tab, where the case's saved trends are listed. Without a starting tab the place opens on
// Figures, as it always did; a tab the person's rights do not offer falls back to Figures.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OPTIONS, json, serve, type Call } from "./reportsTestKit";
import { ReportsPlace } from "./ReportsPlace";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const answers = (call: Call) =>
  call.path === "trends/options" ? json(200, OPTIONS) : call.path === "trends" || call.path === "packs" ? json(200, []) : null;

const place = (props: { initialTab?: "figures" | "trends"; rights?: Set<string> | null } = {}) =>
  render(
    <ReportsPlace apiBaseUrl="http://x" bearerToken="t" investigationId="c1" canDownload={false} rights={props.rights ?? null} initialTab={props.initialTab} />,
  );

const selected = () => screen.getAllByRole("tab").find((t) => t.getAttribute("aria-selected") === "true")?.textContent;

describe("ReportsPlace's starting tab", () => {
  it("opens on Trends when asked to", async () => {
    serve(answers);
    place({ initialTab: "trends" });
    await screen.findByRole("tab", { name: "Trends" });
    expect(selected()).toBe("Trends");
  });

  it("opens on Figures when not asked, as it always did", async () => {
    serve(answers);
    place();
    await screen.findByRole("tab", { name: "Figures" });
    expect(selected()).toBe("Figures");
  });

  it("falls back to Figures when the tab asked for is one the person's rights do not offer", async () => {
    serve(answers);
    place({ initialTab: "trends", rights: new Set(["read_reports"]) });
    await screen.findByRole("tab", { name: "Figures" });
    expect(selected()).toBe("Figures");
  });
});
