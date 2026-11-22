// One way to write a moment on screen: "24 Oct 2026 09:05 UTC". Written by hand, not by Intl: the
// month abbreviation differs between engines ("Sep" or "Sept"). Shared by the case picker's
// untitled cases and the Reports view's POLE footnote.

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function utcStamp(made: Date): string {
  const two = (n: number) => String(n).padStart(2, "0");
  return (
    `${made.getUTCDate()} ${MONTHS[made.getUTCMonth()]} ${made.getUTCFullYear()} ` +
    `${two(made.getUTCHours())}:${two(made.getUTCMinutes())} UTC`
  );
}

/** An ISO moment as `utcStamp` writes it; what the server sent, unchanged, if it is not a date. */
export function utcStampOf(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : utcStamp(at);
}
