/** L3.H1 (ADR-146 decision 4): a run report's drawn-watch count in words. The count is the run's
 * own principal's alone (a drawn watch's alert is its owner's), so it speaks of "your" items. */
export function drawnWatchWords(count: number): string {
  return count === 1
    ? "This load met 1 of your drawn items: its alert is in Rules and Monitoring › Alerts"
    : `This load met ${count} of your drawn items: their alerts are in Rules and Monitoring › Alerts`;
}
