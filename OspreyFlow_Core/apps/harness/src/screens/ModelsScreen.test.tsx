// @vitest-environment jsdom
//
// The guided install's Models screen (ADR-095, ADR-135). Saving the local models must keep the
// providers and defaults the configuration already holds: the screen saves `models` whole, so a
// field it does not send is a field the save drops. The providers are shown read-only, with where
// their keys are given — never a key field on this page (ADR-135 ruling 2 leaves key entry here to
// a separate decision).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { OspreyConfig } from "../api/types";

const client = vi.hoisted(() => ({
  getModelChoices: vi.fn(),
  postConsequences: vi.fn(),
}));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  ...client,
}));

import { ModelsScreen } from "./ModelsScreen";

const CHOICES = {
  extraction: [{ name: "qwen2.5:7b-instruct" }],
  vision: [{ name: "moondream:1.8b-v2-q4_K_M" }],
  transcription: [{ name: "Systran/faster-whisper-tiny.en" }],
  embedding: [{ name: "all-minilm:22m-l6-v2-fp16" }],
  defaults: {
    extraction: "qwen2.5:7b-instruct",
    vision: "moondream:1.8b-v2-q4_K_M",
    transcription: "Systran/faster-whisper-tiny.en",
    embedding: "all-minilm:22m-l6-v2-fp16",
  },
};

const WITH_PROVIDERS = {
  models: {
    local_only: false,
    sendable_handling_codes: ["P"],
    providers: [
      { name: "gemini", label: "Gemini", roles: { extraction: "gemini/gemini-2.5-flash" } },
      { name: "openai", label: "OpenAI", roles: { vision: "openai/gpt-4o-mini" }, api_base: "https://proxy.example" },
    ],
    defaults: { extraction: "gemini" },
    extraction: "qwen2.5:7b-instruct",
  },
} as unknown as OspreyConfig;

beforeEach(() => {
  client.getModelChoices.mockReset().mockResolvedValue(CHOICES);
  client.postConsequences.mockReset().mockResolvedValue({ egress_exception: true, egress_detail: "P may leave." });
});
afterEach(cleanup);

describe("ModelsScreen", () => {
  it("keeps the providers and defaults the configuration holds when it saves", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ModelsScreen config={WITH_PROVIDERS} onSave={onSave} />);
    await screen.findByLabelText("Entity extraction model");
    fireEvent.click(screen.getByRole("button", { name: "Save models" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0]![0] as { models: Record<string, unknown> };
    expect(saved.models.providers).toEqual((WITH_PROVIDERS.models as Record<string, unknown>).providers);
    expect(saved.models.defaults).toEqual({ extraction: "gemini" });
    expect(saved.models.sendable_handling_codes).toEqual(["P"]);
    expect(saved.models.local_only).toBe(false);
  });

  it("keeps the older single provider as well", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const single = {
      models: { local_only: false, provider: { name: "openai", roles: { extraction: "openai/gpt-4o-mini" } } },
    } as unknown as OspreyConfig;
    render(<ModelsScreen config={single} onSave={onSave} />);
    await screen.findByLabelText("Entity extraction model");
    fireEvent.click(screen.getByRole("button", { name: "Save models" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const saved = onSave.mock.calls[0]![0] as { models: Record<string, unknown> };
    expect(saved.models.provider).toEqual({ name: "openai", roles: { extraction: "openai/gpt-4o-mini" } });
    expect(saved.models).not.toHaveProperty("providers");
  });

  it("shows each provider read-only, with its models and the roles it is the default for, and says where keys are given", async () => {
    render(<ModelsScreen config={WITH_PROVIDERS} onSave={vi.fn()} />);
    const table = await screen.findByRole("table", { name: "Model providers" });
    expect(table.textContent).toContain("Gemini");
    expect(table.textContent).toContain("extraction: gemini/gemini-2.5-flash");
    expect(table.textContent).toContain("OSPREY_MODEL_KEY_GEMINI");
    expect(table.textContent).toContain("OSPREY_MODEL_KEY_OPENAI");
    expect(screen.getByText(/ospreyflow models key <name>/)).toBeTruthy();
    // Read-only: nothing on the page takes a key.
    expect(table.querySelector("input, select, textarea")).toBeNull();
    expect(screen.queryByLabelText(/key/i)).toBeNull();
  });

  it("shows no providers table when none is enabled", async () => {
    render(<ModelsScreen config={{ models: { local_only: true } } as unknown as OspreyConfig} onSave={vi.fn()} />);
    await screen.findByLabelText("Entity extraction model");
    expect(screen.queryByRole("table", { name: "Model providers" })).toBeNull();
  });
});
