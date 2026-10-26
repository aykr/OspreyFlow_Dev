// ADR-127 decision 5: what a deduplicating run says about the rows its case already held, in one
// sentence for the Publish run report and Verify's dry run alike.

/** "40 rows already loaded into this case, skipped". `outcome` is "skipped" for a run and
 * "would be skipped" for Verify's dry run. */
export function alreadyLoadedWords(rows: number, outcome: string): string {
  return `${rows} ${rows === 1 ? "row" : "rows"} already loaded into this case, ${outcome}`;
}
