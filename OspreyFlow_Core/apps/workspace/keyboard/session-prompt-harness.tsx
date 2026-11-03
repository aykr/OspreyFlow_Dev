// The session prompt's keyboard harness (ADR-050 Amendment 1, `CLAUDE.md` rule 13): the real
// `SessionPrompt`, the component `App.tsx` shows over whatever screen is open when the token could not
// be renewed, over a page with a field typed into, so the spec can show the page is kept. `?why=`
// chooses the ended or the unreachable form. What its buttons asked for is on `window.__SESSION__`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { SessionPrompt } from "../src/auth/SessionPrompt";

declare global {
  interface Window {
    __SESSION__?: { signInAgain: number; tryAgain: number };
  }
}

window.__SESSION__ = { signInAgain: 0, tryAgain: 0 };
const why = new URLSearchParams(location.search).get("why") === "unreachable" ? "unreachable" : "ended";

function Harness() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <label>
        A sentence being written <input defaultValue="Money straight through an account" />
      </label>
      {open && (
        <SessionPrompt
          why={why}
          onSignInAgain={() => {
            window.__SESSION__!.signInAgain += 1;
            setOpen(false);
          }}
          onTryAgain={() => {
            window.__SESSION__!.tryAgain += 1;
          }}
        />
      )}
    </>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Harness />);
