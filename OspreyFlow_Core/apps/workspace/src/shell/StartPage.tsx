// The bar every surface outside a case shares (ADR-114 Amendment 5 point 9, ADR-115 E1): the marking
// strip, the mark — a way back to Home where one is given — and the account. Home itself
// (`home/HomePage.tsx`, ADR-115 E3) replaced the Start tiles that used to live here.
import type { ReactNode } from "react";

import { BrandMark } from "./BrandMark";
import { ClassificationStrip } from "./ClassificationStrip";

export function StartBar({ account, onStart, marking }: { account: ReactNode; onStart?: () => void; marking: string | null }) {
  return (
    <>
    {marking && <ClassificationStrip marking={marking} />}
    <header className="app-header top-bar">
      {onStart ? (
        <button type="button" className="brand-mark-button" aria-label="OspreyFlow, go to Home" onClick={onStart}>
          <BrandMark />
        </button>
      ) : (
        <BrandMark />
      )}
      <div className="app-header__account" style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
        {account}
      </div>
    </header>
    </>
  );
}
