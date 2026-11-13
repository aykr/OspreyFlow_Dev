// @vitest-environment jsdom
//
// ADR-050 Amendment 3: two edges of the sign-in a refresh now meets. A refusal's own words leave the
// address with the callback's, so the next refresh tries the silent sign-in rather than show the
// refusal again; and signing out forgets the place this tab kept, so the next person starts afresh.
import { afterEach, describe, expect, test, vi } from "vitest";
import { UserManager } from "oidc-client-ts";

import { REFRESH_PLACE_KEY } from "./refreshPlace";
import { clearRedirectCallbackParams, signOut } from "./userManager";

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
  sessionStorage.clear();
});

describe("clearRedirectCallbackParams", () => {
  test("takes the refusal's words out of the address with the callback's, and keeps the rest", () => {
    window.history.replaceState(
      null,
      "",
      "/rules?error=login_required&error_description=Session%20ended&error_uri=x&state=s&iss=i&brand=govuk",
    );
    clearRedirectCallbackParams();
    expect(window.location.pathname).toBe("/rules");
    expect(window.location.search).toBe("?brand=govuk");
  });
});

describe("signOut", () => {
  test("forgets the place this tab kept before going to the identity provider", async () => {
    const signoutRedirect = vi.spyOn(UserManager.prototype, "signoutRedirect").mockResolvedValue(undefined);
    sessionStorage.setItem(REFRESH_PLACE_KEY, "admin");
    await signOut();
    expect(sessionStorage.getItem(REFRESH_PLACE_KEY)).toBeNull();
    expect(signoutRedirect).toHaveBeenCalledTimes(1);
  });
});
