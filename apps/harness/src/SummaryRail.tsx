import { FUTURE_SCREEN_NAMES, SCREEN_NAMES, type ScreenName } from "./store";

export function SummaryRail({ decided }: { decided: Set<ScreenName> }) {
  return (
    <nav aria-label="Setup progress" className="summary-rail">
      <ul>
        {SCREEN_NAMES.map((name) => (
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
    </nav>
  );
}
