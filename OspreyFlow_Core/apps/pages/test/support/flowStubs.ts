import type { CodeFlowProvider } from "../../server/identity.js";

/**
 * The three parts of a `CodeFlowProvider` that a hand-written flow in a case about something else does not use (slice PL9b:
 * renewal, the provider's end-session address and the back-channel logout token). Each says so if it is ever reached, so a
 * case that comes to need one fails at once and in words, not later as something else.
 */
export const unusedFlowParts: Pick<CodeFlowProvider, "refresh" | "endSessionUrl" | "verifyLogoutToken"> = {
  refresh: () => Promise.reject(new Error("this case's flow has no renewal")),
  endSessionUrl: () => Promise.reject(new Error("this case's flow has no end-session address")),
  verifyLogoutToken: () => Promise.reject(new Error("this case's flow has no logout token check")),
};
