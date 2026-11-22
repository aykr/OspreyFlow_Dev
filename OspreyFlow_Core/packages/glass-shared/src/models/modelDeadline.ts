// The Glass's own bound on a call that waits for a model (ADR-135 Amendment 13 (a)): a backstop, so
// no spinner is ever endless. The Conduit stops a hosted engine at its own bound (120 seconds by
// default) and the deployment's own model at 900, each said in words; this is longer than both, so
// it fires only when no answer at all comes back (a proxy holding the connection, a server that
// never replies). The server may still finish after it, so its words promise nothing either way.

/** Sixteen minutes: the Conduit's longest bound (900 seconds) and a minute over. */
export const MODEL_DEADLINE_MS = 960_000;

export const MODEL_DEADLINE_WORDS =
  "No answer came back within 16 minutes, so this stopped waiting. The server may still finish: " +
  "look again in a moment before asking again.";

/** The signal each model call's fetch is given. */
export function modelDeadline(): AbortSignal {
  return AbortSignal.timeout(MODEL_DEADLINE_MS);
}

/** What to say for a fetch that threw: the deadline's words when it fired, else `otherwise`. */
export function unreachedWords(thrown: unknown, otherwise: string): string {
  return thrown instanceof DOMException && thrown.name === "TimeoutError" ? MODEL_DEADLINE_WORDS : otherwise;
}
