// Which domain models a case carries (ADR-126), as three boxes to tick, labelled as the Studio
// labels them. None ticked is the POLE core model, said beside the boxes so an empty choice is not
// mistaken for an unanswered one. Shared by a new case's form and a case's own "Domain models".
import { Checkbox } from "../design/primitives/Checkbox";
import { DOMAIN_PACKS, type DomainPack, POLE_LABEL, sortedDomains } from "./cases";

export interface DomainChoiceProps {
  chosen: readonly DomainPack[];
  onChange: (chosen: DomainPack[]) => void;
  legend?: string;
  disabled?: boolean;
}

export function DomainChoice({ chosen, onChange, legend = "Domain models", disabled }: DomainChoiceProps) {
  return (
    <fieldset
      aria-label={legend}
      style={{ border: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}
    >
      <legend className="label" style={{ marginBottom: "var(--sp-4)" }}>
        {legend}
      </legend>
      {DOMAIN_PACKS.map((pack) => (
        <label key={pack.name} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          <Checkbox
            checked={chosen.includes(pack.name)}
            disabled={disabled}
            onChange={(event) =>
              onChange(
                sortedDomains(
                  event.target.checked ? [...chosen, pack.name] : chosen.filter((n) => n !== pack.name),
                ),
              )
            }
          />
          {pack.label}
        </label>
      ))}
      {chosen.length === 0 && <span className="label">{POLE_LABEL}</span>}
    </fieldset>
  );
}
