// The phase banner (ADR-132). Under `govuk` the markup follows GOV.UK Frontend 6.6.0's `phase-banner`
// component; under OspreyFlow it is a plain banner styled by the workspace's own classes. Both expose
// the same "Service phase" landmark. Nothing is drawn for `live` or `none`.
import { currentBrand, type Phase } from "../brand";

export function PhaseBanner({ phase }: { phase: Phase }) {
  if (phase !== "alpha" && phase !== "beta") return null;
  const tag = phase === "alpha" ? "Alpha" : "Beta";
  if (currentBrand() === "govuk") {
    return (
      <div className="govuk-phase-banner govuk-width-container" role="region" aria-label="Service phase">
        <p className="govuk-phase-banner__content">
          <strong className="govuk-tag govuk-phase-banner__content__tag">{tag}</strong>
          <span className="govuk-phase-banner__text">This is a new service.</span>
        </p>
      </div>
    );
  }
  return (
    <div className="phase-banner" role="region" aria-label="Service phase">
      <strong className="phase-banner__tag">{tag}</strong> <span>This is a new service.</span>
    </div>
  );
}
