// ADR-148 Amendment 8 (the orchestrator's reviews of P10 part 2): when the Conduit cannot say who the
// person is (`GET /v1/me` did not answer), nothing it gates is offered, and the person is told so in
// words, with *Try again* (which asks again) and *Sign out* within reach. Its own component so the
// keyboard walkthrough and the axe scan reach it on a harness (`account-unread-harness.html`; rule 13).
import { Button } from "../design/primitives/Button";

export const ACCOUNT_UNREAD_WORDS =
  "Your account could not be read just now, so nothing is offered.";

export function AccountUnread({
  onTryAgain,
  onSignOut,
}: {
  onTryAgain: () => void;
  onSignOut: () => void;
}) {
  return (
    <div
      role="alert"
      style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}
    >
      <span>{ACCOUNT_UNREAD_WORDS}</span>
      <Button onClick={onTryAgain}>Try again</Button>
      <Button onClick={onSignOut}>Sign out</Button>
    </div>
  );
}
