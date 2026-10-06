// The shell's icons (ADR-097 step 1): 16px, one stroke in the current text colour, no fill, so
// they take the chrome's neutral and never a data colour.
export type ShellIcon = "cases" | "history" | "watches" | "types" | "ingest" | "glass" | "names";

const PATHS: Record<ShellIcon, string> = {
  // Two stacked folders: the case and its branches.
  cases: "M2 4.5h4l1.5 1.5H14v7H2z M4 2.5h3l1 1",
  // A clock face.
  history: "M8 2.5a5.5 5.5 0 1 0 0 11a5.5 5.5 0 0 0 0-11z M8 5v3.2l2.2 1.3",
  // A bell: something to be told about.
  watches: "M4 11V7.5a4 4 0 0 1 8 0V11l1 1.5H3z M6.8 13.5a1.3 1.3 0 0 0 2.4 0",
  // A tag: a type of link.
  types: "M2.5 2.5h5l6 6l-5 5l-6-6z M5.2 5.2h.1",
  // A tray with an arrow into it: bringing data in.
  ingest: "M2.5 9.5h3l1 2h3l1-2h3V13h-11z M8 2.5v6 M5.5 6L8 8.5L10.5 6",
  // Three linked points: the graph.
  glass: "M4 4.5a1.5 1.5 0 1 0 0 .01 M12 4.5a1.5 1.5 0 1 0 0 .01 M8 12a1.5 1.5 0 1 0 0 .01 M5.3 5.3L7.2 10.8 M10.7 5.3L8.8 10.8 M5.5 4.5h5",
  // Two arrows apart: show the names.
  names: "M2.5 8h11 M10.5 5l3 3l-3 3",
};

export function Icon({ name }: { name: ShellIcon }) {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
      <path d={PATHS[name]} />
    </svg>
  );
}
