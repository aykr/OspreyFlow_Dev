// The skip link (ADR-132), drawn under both brands. Under `govuk` it follows GOV.UK Frontend 6.6.0's
// `skip-link` component. The click handler moves focus itself, since the target is a non-link
// element that a bare fragment jump does not always focus. Enter on a link fires click.
import type { MouseEvent } from "react";

import { currentBrand } from "../brand";

export function SkipLink({ target = "main-content" }: { target?: string }) {
  const govuk = currentBrand() === "govuk";
  function skip(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    const element = document.getElementById(target);
    if (!element) return;
    element.focus();
    element.scrollIntoView?.();
  }
  return (
    <a
      href={"#" + target}
      className={govuk ? "govuk-skip-link" : "skip-link"}
      {...(govuk ? { "data-module": "govuk-skip-link" } : {})}
      onClick={skip}
    >
      Skip to main content
    </a>
  );
}
