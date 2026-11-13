// The phase banner (ADR-132). Under `govuk` the markup follows GOV.UK Frontend 6.6.0's `phase-banner`
// component; under OspreyFlow it is a plain banner styled by the workspace's own classes. Both expose
// the same "Service phase" landmark. At `alpha` or `beta` it shows the phase's tag and its words; with
// the deployment's own words (`appearance.banner_text`, ADR-132 Amendment 7) those replace "This is a
// new service.", and at `live` or `none` they are shown alone. With neither, nothing is drawn.
import { currentBrand, type Phase } from "../brand";

export function PhaseBanner({ phase, text }: { phase: Phase; text?: string }) {
  const words = text?.trim() ? text : null;
  const tag = phase === "alpha" ? "Alpha" : phase === "beta" ? "Beta" : null;
  if (!tag && !words) return null;
  const said = words ?? "This is a new service.";
  if (currentBrand() === "govuk") {
    return (
      <div className="govuk-phase-banner govuk-width-container" role="region" aria-label="Service phase">
        <p className="govuk-phase-banner__content">
          {tag && <strong className="govuk-tag govuk-phase-banner__content__tag">{tag}</strong>}
          <span className="govuk-phase-banner__text">{said}</span>
        </p>
      </div>
    );
  }
  return (
    <div className="phase-banner" role="region" aria-label="Service phase">
      {tag && (
        <>
          <strong className="phase-banner__tag">{tag}</strong>{" "}
        </>
      )}
      <span>{said}</span>
    </div>
  );
}
