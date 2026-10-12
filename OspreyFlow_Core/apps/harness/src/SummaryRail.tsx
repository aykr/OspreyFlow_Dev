import { ThemeToggle } from "../../workspace/src/theme/ThemeToggle";
import { FUTURE_SCREEN_NAMES, SCREEN_NAMES } from "./store";

export function SummaryRail({
  decided,
  ingestRoot,
  screens = SCREEN_NAMES,
}: {
  decided: ReadonlySet<string>;
  /** The screens to list; the Set-up console's own six unless the guided install page names its
   * chosen mode's. */
  screens?: readonly string[];
  /** Owner ruling R6, 27 September 2026 — shown here because it is the one configured path an
   * *operator* has to act on after Launch: analysts can only ingest what is placed in it, so a
   * rail that never names it leaves the folder undiscoverable. */
  ingestRoot?: string;
}) {
  return (
    <nav aria-label="Setup progress" className="summary-rail">
      <ul>
        {screens.map((name) => (
          <li key={name}>
            <span aria-hidden="true">{decided.has(name) ? "✓" : "○"}</span>{" "}
            <span>{name}</span>{" "}
            <span className="summary-rail__status">
              {decided.has(name) ? "decided" : "outstanding"}
            </span>
          </li>
        ))}
        {FUTURE_SCREEN_NAMES.map((name) => (
          <li key={name} className="summary-rail__future">
            <span aria-hidden="true">○</span> <span>{name}</span>{" "}
            <span className="summary-rail__status">not built yet (Stage 2 §6 part B/C)</span>
          </li>
        ))}
      </ul>
      {ingestRoot ? (
        <p className="summary-rail__status">
          Ingest folder: <code>{ingestRoot}</code>
        </p>
      ) : null}
      <p>
        <ThemeToggle />
      </p>
    </nav>
  );
}
