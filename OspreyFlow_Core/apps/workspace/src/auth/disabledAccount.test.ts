// ADR-148 Amendment 8: the disabled-account words only when the Conduit's 401 says exactly that.
import { describe, expect, it } from "vitest";

import { CONDUIT_DISABLED_DETAIL, isDisabledRefusal } from "./disabledAccount";

const answer = (status: number, body: string) => new Response(body, { status });

describe("a refusal is a disabled account's", () => {
  it("only on a 401 whose detail is the Conduit's words exactly", async () => {
    expect(await isDisabledRefusal(answer(401, JSON.stringify({ detail: CONDUIT_DISABLED_DETAIL })))).toBe(true);
  });

  it.each([
    ["another 401", answer(401, JSON.stringify({ detail: "token rejected: Signature has expired" }))],
    ["the words on a 403", answer(403, JSON.stringify({ detail: CONDUIT_DISABLED_DETAIL }))],
    ["the words inside other words", answer(401, JSON.stringify({ detail: `x ${CONDUIT_DISABLED_DETAIL}` }))],
    ["a body that is not JSON", answer(401, "<html>")],
    ["no body", answer(401, "")],
  ])("never from %s", async (_why, refusal) => {
    expect(await isDisabledRefusal(refusal)).toBe(false);
  });
});
