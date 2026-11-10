/** L3.H1 (ADR-146 decision 4): a run report's drawn-watch count in words. The count is of alerts
 * (one per drawn item and loaded node in each case), and of the run's own principal's alone (a
 * drawn watch's alert is its owner's), so it speaks of "your" drawn items. */
export function drawnWatchWords(count: number): string {
  return count === 1
    ? "This load raised 1 alert on your drawn items: it is in Rules and Monitoring › Alerts"
    : `This load raised ${count} alerts on your drawn items: they are in Rules and Monitoring › Alerts`;
}
