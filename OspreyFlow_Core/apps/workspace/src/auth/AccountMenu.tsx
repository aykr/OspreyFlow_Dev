import { DropdownPanel } from "../design/primitives/DropdownPanel";
import { ThemeToggle } from "../theme/ThemeToggle";
import type { DisplayPrincipal } from "./userManager";

export interface AccountMenuProps {
  principal: DisplayPrincipal;
  onSignOut: () => void;
}

/** The signed-in account (ADR-050, ADR-065): the user name and clearance stay on the button, so
 * the clearance is always visible; the subject, unit and Sign out are behind it. Informational
 * only. The Glass derives nothing from any of it. */
export function AccountMenu({ principal, onSignOut }: AccountMenuProps) {
  const who = principal.username || principal.sub;
  return (
    <DropdownPanel
      label={
        <>
          <span className="menu-button__name">{who}</span>
          <span className="menu-button__fixed"> · {principal.clearance}</span>
        </>
      }
      title={`${who} · ${principal.clearance}`}
      panelLabel="Account menu"
      alignRight
      buttonClassName="menu-button--account"
    >
      {(close) => (
        <>
          <div>
            <div className="menu-panel__term">Subject</div>
            <div className="menu-panel__value">{principal.sub}</div>
          </div>
          <div>
            <div className="menu-panel__term">Clearance</div>
            <div className="menu-panel__value">{principal.clearance}</div>
          </div>
          {principal.orgUnit && (
            <div>
              <div className="menu-panel__term">Unit</div>
              <div className="menu-panel__value">{principal.orgUnit}</div>
            </div>
          )}
          <hr className="menu-panel__rule" />
          {/* ADR-097 step 3: the theme is the account's preference, so it is here, not in the bar. */}
          <ThemeToggle className="menu-panel__item" />
          <button
            type="button"
            className="menu-panel__item"
            onClick={() => {
              close();
              onSignOut();
            }}
          >
            Sign out
          </button>
        </>
      )}
    </DropdownPanel>
  );
}
