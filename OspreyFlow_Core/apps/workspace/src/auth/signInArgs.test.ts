// ADR-115 decision 3: *Continue with organisation sign-in* goes straight to the brokered provider —
// Keycloak's `kc_idp_hint` on the authorisation request; the OspreyFlow account goes to Keycloak's own
// form, with no hint.
import { describe, expect, it } from "vitest";

import { signInArgs } from "./userManager";

describe("the sign-in request", () => {
  it("names the organisation's provider only when asked to", () => {
    expect(signInArgs("acme-entra")).toEqual({ extraQueryParams: { kc_idp_hint: "acme-entra" } });
    expect(signInArgs(undefined)).toBeUndefined();
  });
});
