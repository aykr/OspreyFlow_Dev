// ADR-135 Amendment 13 (a): every Glass call that waits for a model has a deadline, and says so in
// words when it fires; and an engine's refusal reaches the person in the Conduit's words. Shown red
// before the change: no call carried a signal, and patterns/ask said a refusal as a status number.
import { afterEach, describe, expect, it, vi } from "vitest";

import { extractEmail } from "../inspector/linkEventsApi";
import { askToSearch } from "../patterns/api";
import { askQuestion } from "../questions/questionsApi";
import { extractDocument } from "../reader/readerApi";
import { MODEL_DEADLINE_MS, MODEL_DEADLINE_WORDS } from "./modelDeadline";

/** Each Glass call that waits for a model, as its screen makes it. */
const CALLS: [string, () => Promise<unknown>][] = [
  ["Ask", () => askQuestion("", "t", "c1", "Who?")],
  ["patterns/ask", () => askToSearch("", "t", "c1", "Who?", [])],
  ["a document's extraction", () => extractDocument("", "t", "c1", "d1", "model")],
  ["an email's extraction", () => extractEmail("", "t", "c1", "e1", "ev1", "model")],
];

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("a call that waits for a model", () => {
  it.each(CALLS)("%s is given the deadline", async (_name, call) => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    const fetch = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await call().catch(() => undefined);
    expect(timeout).toHaveBeenCalledWith(MODEL_DEADLINE_MS);
    const init = (fetch.mock.calls[0] as unknown[])[1] as RequestInit;
    expect(init.signal).toBe(timeout.mock.results[0]?.value);
  });

  it.each(CALLS)("%s says the deadline in words when it fires", async (_name, call) => {
    // What a fetch aborted by `AbortSignal.timeout` rejects with: the signal's reason.
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new DOMException("signal timed out", "TimeoutError"))));
    await expect(call()).rejects.toThrow(MODEL_DEADLINE_WORDS);
  });

  it.each(CALLS)("%s still says an unreachable server as before", async (_name, call) => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(call()).rejects.toThrow("The server could not be reached.");
  });

  it.each(CALLS)("%s shows an engine's refusal in the Conduit's words", async (_name, call) => {
    const detail = "Gemini is refusing more requests just now. Nothing was recorded.";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ error: "model_engine_refused", kind: "busy", detail }), { status: 429 }),
      ),
    );
    await expect(call()).rejects.toThrow(detail);
  });
});
