// ADR-131: a source row is stored as its offset under the header, so the first data row is
// `row 0`; a person counts from 1. Every place the Glass shows a row reads it through here.

const ROW_LOCATOR = /^row (\d+)$/;

/** A stored row offset as a person counts it: the first data row is 1. */
export function rowNumber(index: number): number {
  return index + 1;
}

/** A source's locator as it is shown: `row N` counted from 1, any other form as stored. */
export function locatorText(locator: string): string {
  const match = ROW_LOCATOR.exec(locator);
  return match ? `row ${rowNumber(Number(match[1]))}` : locator;
}
