// The workspace welcome panel's keyboard harness (ADR-115 E6, `CLAUDE.md` rule 13): the real panel and
// the real `?` hook the Glass uses; the history routes are answered by `welcome.spec.ts`. What was
// restored is on `window.__WELCOME__`.
import { useCallback, useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { useHelpKey, WorkspaceWelcome } from "../src/welcome/WorkspaceWelcome";

declare global {
  interface Window {
    __WELCOME__?: { restored: number[] };
  }
}
window.__WELCOME__ = { restored: [] };

function Harness() {
  const [open, setOpen] = useState(false);
  useHelpKey(useCallback(() => setOpen(true), []));
  return (
    <>
      <input aria-label="A text field" />
      {open && (
        <WorkspaceWelcome
          apiBaseUrl="http://keyboard-test.invalid"
          bearerToken="unused"
          investigationId="c1"
          nodeCount={25}
          onRestored={(delta) => window.__WELCOME__!.restored.push((delta as { seq: number }).seq)}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
