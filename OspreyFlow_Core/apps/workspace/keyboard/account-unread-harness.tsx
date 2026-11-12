// The top bar when the Conduit cannot say who the person is (ADR-148 Amendment 8): the words, *Try
// again* and *Sign out*, on their own, for `account-unread.spec.ts` (rule 13) and the every-harness axe
// scan in both themes and under GOV.UK (`?brand=govuk`). What each button did is recorded on
// `window.__acted`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/shell/chrome.css";
import { AccountUnread } from "../src/auth/AccountUnread";
import { applyHarnessBrand } from "./brandHarness";

await applyHarnessBrand();

const acted: string[] = [];
(window as unknown as { __acted: string[] }).__acted = acted;

function Harness() {
  return (
    <header className="app-header top-bar" data-app="glass">
      <h1 className="label" style={{ margin: 0 }}>
        Account unread harness
      </h1>
      <div
        className="app-header__account"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-8)",
          marginLeft: "auto",
        }}
      >
        <AccountUnread
          onTryAgain={() => acted.push("try-again")}
          onSignOut={() => acted.push("sign-out")}
        />
      </div>
    </header>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
