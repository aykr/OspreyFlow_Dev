// @vitest-environment jsdom
//
// The Set-up console's Geospatial screen (ADR-147 decision 6; Amendment 2, ruling 8): Build runs the
// Conduit's own build, which requires the unit the gazetteer's places are held by. The screen sends
// the unit typed, and shows the Conduit's refusal in its own words.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({ buildLocalBasemap: vi.fn() }));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  ...client,
}));

import { ApiError } from "../api/client";
import { GeospatialScreen } from "./GeospatialScreen";

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("GeospatialScreen's Build", () => {
  it("sends the region and the unit typed", async () => {
    client.buildLocalBasemap.mockResolvedValue({ returncode: 0, lines: ["Built rutland.pmtiles."] });
    render(<GeospatialScreen />);
    fireEvent.change(screen.getByLabelText("Unit that holds the place names"), {
      target: { value: "unit-7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Build local basemap" }));
    await waitFor(() => expect(client.buildLocalBasemap).toHaveBeenCalledWith("rutland", "unit-7"));
    expect(await screen.findByText(/Built rutland\.pmtiles\./)).toBeTruthy();
  });

  it("shows the refusal of a build without a unit in words", async () => {
    client.buildLocalBasemap.mockRejectedValue(
      new ApiError(
        422,
        "name the unit the gazetteer's places are held by, as the deployment names it (up to 60 characters)",
      ),
    );
    render(<GeospatialScreen />);
    fireEvent.click(screen.getByRole("button", { name: "Build local basemap" }));
    expect(await screen.findByText(/name the unit the gazetteer's places are held by/)).toBeTruthy();
    expect(client.buildLocalBasemap).toHaveBeenCalledWith("rutland", "");
  });
});
