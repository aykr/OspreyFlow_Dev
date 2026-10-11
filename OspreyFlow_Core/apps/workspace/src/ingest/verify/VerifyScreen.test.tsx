// @vitest-environment jsdom
// The preview is a dry run: nothing it draws is stored, so its canvas is given no case to ask the
// Conduit about. Found live, 11 October 2026 — it was handed the recipe id as a case id, and asked
// `/v1/investigations/<recipe id>/pictures` for pictures of nodes that do not exist.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const canvasProps: Record<string, unknown>[] = [];
vi.mock("../../canvas/GlassCanvas", () => ({
  GlassCanvas: (props: Record<string, unknown>) => {
    canvasProps.push(props);
    return <div>preview canvas</div>;
  },
}));
vi.mock("../api", () => ({
  ProfileError: class extends Error {},
  fetchDraft: vi.fn(async () => ({ name: "Onboarding" })),
  fetchOntologySchema: vi.fn(async () => ({ entity_types: [], edge_types: [] })),
  runVerify: vi.fn(async () => ({ nodes: [], edges: [], entities_by_type: {}, edges_by_type: {} })),
}));

import { VerifyScreen } from "./VerifyScreen";

afterEach(cleanup);

describe("the Verify preview", () => {
  it("draws the dry run on a canvas that asks the Conduit nothing", async () => {
    render(<VerifyScreen apiBaseUrl="http://x" investigationId="case-1" bearerToken="t" recipeId="recipe-1" onBack={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: /Run verify/i }));
    await screen.findByText("preview canvas");
    await waitFor(() => expect(canvasProps.length).toBeGreaterThan(0));
    const props = canvasProps.at(-1) ?? {};
    expect(props.investigationId).not.toBe("recipe-1");
    expect(props.bearerToken).toBe("");
  });

  it("goes back to the pipeline, and says so", async () => {
    // Since ADR-108 every stage editor returns to the canvas; the button said "← Connect" (survey, 11 Oct).
    render(<VerifyScreen apiBaseUrl="http://x" investigationId="case-1" bearerToken="t" recipeId="recipe-1" onBack={() => undefined} />);
    expect(await screen.findByRole("button", { name: "← Back to the pipeline" })).toBeTruthy();
  });
});
