// The administrator's *Proposed types* list (ADR-090 C3) on its own, opened by the same top-bar
// button `App.tsx` shows a holder of `osprey-admin`. The routes are answered by the spec at the
// transport (`proposed-types.spec.ts`); each decision is counted on `window.__DECIDED__`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { Button } from "../src/design/primitives/Button";
import { ProposedTypes } from "../src/linktypes/ProposedTypes";

declare global {
  interface Window {
    __DECIDED__?: number;
  }
}
window.__DECIDED__ = 0;

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button aria-pressed={open} onClick={() => setOpen(true)}>
        Proposed types
      </Button>
      <ProposedTypes
        apiBaseUrl="http://keyboard-test.invalid"
        bearerToken="unused"
        open={open}
        onClose={() => setOpen(false)}
        onDecided={() => {
          window.__DECIDED__ = (window.__DECIDED__ ?? 0) + 1;
        }}
      />
    </>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Harness />);
