// @vitest-environment jsdom
//
// The guided install's Models screen (ADR-095, ADR-135). Saving the local models must keep the
// providers and defaults the configuration already holds: the screen saves `models` whole, so a
// field it does not send is a field the save drops. The providers are shown read-only, with where
// their keys are given. On the guided install page only (`keyEntry`), each has a write-only key
// field (ADR-137 decision 3): sent to the install page's own server, cleared once sent, and the page
// says only "key set" or "no key". The Set-up console has no key field.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { OspreyConfig } from "../api/types";

const client = vi.hoisted(() => ({
  getModelChoices: vi.fn(),
  postConsequences: vi.fn(),
  getInstallKeys: vi.fn(),
  putInstallKey: vi.fn(),
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

const GEMINI_KEY = "AIza-gemini-NEVER-SHOWN-0123456789";

beforeEach(() => {
  client.getInstallKeys.mockReset().mockResolvedValue({
    providers: [
      { name: "gemini", label: "Gemini", variable: "OSPREY_MODEL_KEY_GEMINI", set: false },
      { name: "openai", label: "OpenAI", variable: "OSPREY_MODEL_KEY_OPENAI", set: true },
    ],
  });
  client.putInstallKey.mockReset().mockResolvedValue({ name: "gemini", set: true });
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

  it("asks for no key, and the install page for none, outside the guided install", async () => {
    render(<ModelsScreen config={WITH_PROVIDERS} onSave={vi.fn()} />);
    await screen.findByRole("table", { name: "Model providers" });
    expect(client.getInstallKeys).not.toHaveBeenCalled();
    expect(document.querySelector('input[type="password"]')).toBeNull();
  });

  it("on the guided install, has a write-only key field per provider and says whether each key is set", async () => {
    render(<ModelsScreen config={WITH_PROVIDERS} onSave={vi.fn()} keyEntry />);
    const gemini = await screen.findByLabelText("Key for Gemini");
    const openai = screen.getByLabelText("Key for OpenAI");
    for (const field of [gemini, openai]) {
      expect(field.getAttribute("type")).toBe("password");
      expect(field.getAttribute("autocomplete")).toBe("off");
      expect((field as HTMLInputElement).value).toBe("");
    }
    const table = screen.getByRole("table", { name: "Model providers" });
    await waitFor(() => expect(table.textContent).toContain("no key"));
    expect(table.textContent).toContain("key set");
  });

  it("sends the key to the install page, clears the field and shows key set — never the key", async () => {
    client.getInstallKeys
      .mockResolvedValueOnce({
        providers: [
          { name: "gemini", label: "Gemini", variable: "OSPREY_MODEL_KEY_GEMINI", set: false },
          { name: "openai", label: "OpenAI", variable: "OSPREY_MODEL_KEY_OPENAI", set: false },
        ],
      });
    render(<ModelsScreen config={WITH_PROVIDERS} onSave={vi.fn()} keyEntry />);
    const field = (await screen.findByLabelText("Key for Gemini")) as HTMLInputElement;
    await waitFor(() => expect(screen.getAllByText("no key")).toHaveLength(2));
    fireEvent.change(field, { target: { value: GEMINI_KEY } });
    fireEvent.click(screen.getByRole("button", { name: "Set the key for Gemini" }));
    await waitFor(() => expect(client.putInstallKey).toHaveBeenCalledWith("gemini", GEMINI_KEY));
    await waitFor(() => expect(field.value).toBe(""));
    expect(screen.getByText("key set")).toBeTruthy();
    expect(document.body.innerHTML).not.toContain(GEMINI_KEY);
  });

  it("says why a key was refused, and keeps no key on the page", async () => {
    client.putInstallKey.mockRejectedValue(
      Object.assign(new Error("refused"), { body: JSON.stringify({ error: "A key has no spaces or line breaks in it." }) }),
    );
    render(<ModelsScreen config={WITH_PROVIDERS} onSave={vi.fn()} keyEntry />);
    const field = (await screen.findByLabelText("Key for Gemini")) as HTMLInputElement;
    fireEvent.change(field, { target: { value: "two words" } });
    fireEvent.click(screen.getByRole("button", { name: "Set the key for Gemini" }));
    expect((await screen.findByRole("alert")).textContent).toContain("no spaces");
    expect(field.value).toBe("");
  });

  it("shows no providers table when none is enabled", async () => {
    render(<ModelsScreen config={{ models: { local_only: true } } as unknown as OspreyConfig} onSave={vi.fn()} />);
    await screen.findByLabelText("Entity extraction model");
    expect(screen.queryByRole("table", { name: "Model providers" })).toBeNull();
  });
});
