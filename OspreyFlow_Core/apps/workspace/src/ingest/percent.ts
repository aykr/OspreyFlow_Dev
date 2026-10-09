/** A share of a column's values as the Profile and Map stages show it. A rounded figure never
 * claims all or none when that is not so: 239 of 240 matched once read "100%" and hid the row that
 * will be rejected (9 October 2026). Near either end it keeps one decimal, held between 0.1% and
 * 99.9%; elsewhere it is a whole number. */
export function percent(rate: number): string {
  const value = rate * 100;
  const whole = Math.round(value);
  const tenth = Math.round(value * 10) / 10;
  if (whole === 100 && rate < 1) return `${Math.min(tenth, 99.9)}%`;
  if (whole === 0 && rate > 0) return `${Math.max(tenth, 0.1)}%`;
  return `${whole}%`;
}
