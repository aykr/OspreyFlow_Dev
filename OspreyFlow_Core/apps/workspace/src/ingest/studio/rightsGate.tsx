// An action a person can't take says why and who can, never only greyed out (ADR-145 Amendment 4
// decision 12; L1.8). The Studio's actions that need a right each take it from here: the button stays
// focusable (`aria-disabled`, so a keyboard reaches it and its tip, rule 13), does nothing when pressed,
// and is described by a tip in words from `help/roles.ts` — the right's name and the built-in roles that
// hold it, never a role id or a person (the owner's ruling of 9 November 2026, ADR-145 Amendment 7).
// The route refuses all the same (rule 3): this is words, not access control.
import { createContext, useContext, useId, type MouseEvent } from "react";

import { Button, type ButtonProps } from "../../design/primitives/Button";
import { whyNotByRole, type Right } from "../../help/roles";

/** The person's rights (`GET /v1/me/rights`) for the Studio's actions. `null` while they are not known:
 * every action is then offered as before, and the route answers for itself. */
export const StudioRights = createContext<ReadonlySet<string> | null>(null);

/** Why the person cannot take an action needing `rights` (every one of them), or `null` if they can. */
export function useWhyNot(rights: Right | readonly Right[]): string | null {
  const held = useContext(StudioRights);
  if (held === null) return null;
  const missing = (typeof rights === "string" ? [rights] : rights).find((r) => !held.has(r));
  return missing === undefined ? null : whyNotByRole(missing);
}

export interface RightButtonProps extends ButtonProps {
  /** The right (or rights) the action's route checks, read from the route's own declaration. */
  right: Right | readonly Right[];
}

/** A Studio button that needs a right: as `Button` for whoever holds it; otherwise focusable, inert and
 * described by why and who can. */
export function RightButton({ right, onClick, disabled, style, ...rest }: RightButtonProps) {
  const why = useWhyNot(right);
  const tip = useId();
  if (why === null) return <Button {...rest} style={style} disabled={disabled} onClick={onClick} />;
  const refuse = (event: MouseEvent<HTMLButtonElement>) => event.preventDefault();
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--sp-8)", flexWrap: "wrap" }}>
      <Button
        {...rest}
        aria-disabled="true"
        aria-describedby={tip}
        onClick={refuse}
        style={{ ...style, color: "var(--text-disabled)", cursor: "not-allowed" }}
      />
      <span id={tip} className="label" data-why-not="">
        {why}
      </span>
    </span>
  );
}

/** A line saying why a whole part of the Studio is closed to the person, and who can open it. */
export function WhyNotLine({ right }: { right: Right | readonly Right[] }) {
  const why = useWhyNot(right);
  return why === null ? null : (
    <p className="label" data-why-not="" style={{ margin: 0 }}>
      {why}
    </p>
  );
}
