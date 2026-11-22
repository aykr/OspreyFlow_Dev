import type { SessionEventReporter } from "../../server/sessionEvents.js";

/**
 * A reporter that reports nothing: for the cases about the `/v1` forwarder, the live stream and the body stall, whose
 * fake Conduit counts every connection and every request it gets, so that a sign-in's own report to it (SE8c) would be
 * counted as something the case under test did. The reports themselves are the business of `sign-in-events.test.ts`.
 */
export const noSessionEvents: SessionEventReporter = {
  async report() {},
  async settled() {},
  misses: 0,
};
