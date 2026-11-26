/**
 * What a page may send on to the Conduit as an identifier taken from its own query (a case, a pack): a plain name, and nothing else.
 *
 * `v1()` (`conduit.ts`) encodes each segment, but the Conduit decodes `%2F` to `/` before it routes, so an identifier holding a slash
 * would reach another real route as the person (`X%2Fownership` is a node's ownership read, `X%2Falert-queue` is `explain_alert`, which
 * writes an audit row; `pack-estuary%2Fpublished` is the published read). A `.` or `..` segment is folded away by a client. Neither is an
 * identifier, whatever encoding hides it. Real ones are ULIDs.
 *
 * One place, so the pages that take an identifier hold to the same rule (`packTrends.ts`, `alertQueue.ts`).
 */

/** The longest identifier a page will ask about; a longer one is a path nothing serves. */
export const MAX_ID_CHARS = 200;

/** A plain name: letters, digits, dots, underscores and hyphens, starting with a letter or a digit. */
export const PLAIN_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

/** One query value, given once: anything else (missing, repeated, empty, too long, not a plain name) is not an identifier. */
export function identifier(value: unknown): string | undefined {
  return typeof value === "string" && value.length <= MAX_ID_CHARS && PLAIN_NAME.test(value) ? value : undefined;
}
