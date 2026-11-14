import { describe, expect, test } from "vitest";

import { isDisabledRefusal } from "./disabledAccount";
import { actionableRefusalWords } from "./refusalWords";

const answer = (body: unknown, status = 401) => new Response(JSON.stringify(body), { status });

describe("a refusal the person can act on is shown in the Conduit's words (ADR-148 Amendments 15, 17, 18)", () => {
  test.each([
    ["access_not_set", "your clearance has not been set in this deployment: ask an administrator to set it in Admin › People"],
    ["token_version", "this deployment's app registration issues version 1 access tokens: set requestedAccessTokenVersion to 2"],
    ["guest_not_admitted", "guest accounts are not admitted to this deployment: ask an administrator"],
  ])("%s shows its words", async (error, detail) => {
    expect(await actionableRefusalWords(answer({ detail, error }))).toBe(detail);
  });

  test.each([
    ["an untagged 401", answer({ detail: "token rejected: Invalid audience" })],
    ["an unknown tag", answer({ detail: "something else", error: "not_a_tag" })],
    ["a tagged answer that is not a 401", answer({ detail: "words", error: "access_not_set" }, 403)],
    ["a tag with no words", answer({ error: "token_version" })],
    ["a tag with empty words", answer({ detail: " ", error: "token_version" })],
    ["a body that is not JSON", new Response("<html>", { status: 401 })],
    ["no body", new Response(null, { status: 401 })],
  ])("%s shows none", async (_, refusal) => {
    expect(await actionableRefusalWords(refusal)).toBeNull();
  });

  test("the refusal's own body is still there for the disabled check that reads it next", async () => {
    const refusal = answer({ detail: "this account is disabled in this deployment: ask an administrator" });
    expect(await actionableRefusalWords(refusal)).toBeNull();
    expect(await isDisabledRefusal(refusal)).toBe(true);
  });
});
