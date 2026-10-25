// A refused Connect save says why, in the server's words, whichever shape the 422 takes: the coded
// `source_declarations_invalid` body, or FastAPI's own validation list when the body fails
// `ConnectDraftInput` before the route runs (ADR-127 Amendment 2).
import { afterEach, describe, expect, it, vi } from "vitest";

import { createDraft, updateDraft } from "./api";

afterEach(() => vi.unstubAllGlobals());

const INPUT = { label: "L", connector_profile: "generic-csv", handling: {} };

function refuse(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      status,
      json: async () => {
        if (body === undefined) throw new SyntaxError("not json");
        return body;
      },
    })),
  );
}

const create = () => createDraft("http://api", "t", "inv-1", INPUT).catch((e: unknown) => e as Error);
const update = () => updateDraft("http://api", "t", "inv-1", "r1", INPUT).catch((e: unknown) => e as Error);

describe("a refused draft save", () => {
  it("reads the detail of the coded source_declarations_invalid body", async () => {
    refuse(422, { error: "source_declarations_invalid", detail: "handling units must be a list of non-empty unit names" });
    expect((await update()).message).toBe("handling units must be a list of non-empty unit names");
  });

  it("reads the first msg of FastAPI's validation list", async () => {
    refuse(422, {
      detail: [
        { loc: ["body", "handling"], msg: "Value error, handling units must be a list of non-empty unit names", type: "value_error" },
        { loc: ["body", "label"], msg: "Field required", type: "missing" },
      ],
    });
    expect((await create()).message).toBe("Value error, handling units must be a list of non-empty unit names");
  });

  it("falls back to the status for a 422 it cannot read", async () => {
    refuse(422, { detail: [] });
    expect((await create()).message).toBe("POST /v1/ingest/recipes failed: 422");
    refuse(422, undefined);
    expect((await update()).message).toBe("PATCH /v1/ingest/recipes/{id} failed: 422");
  });

  it("does not take another coded 422's detail for a declaration cause", async () => {
    refuse(422, { error: "something_else", detail: "not for this" });
    expect((await create()).message).toBe("POST /v1/ingest/recipes failed: 422");
  });
});
