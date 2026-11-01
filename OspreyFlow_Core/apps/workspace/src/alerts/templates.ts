// The rule templates (`06_DECISIONS.md` ADR-133 decision 2, stage (a)): the seven typologies a case
// rule can run, each offered as a named template with its defaults, grouped by the work it serves.
// Using one fills the rule form; the Author still names it and deploys it. Stage (c) added the four
// new AML templates (a high-risk jurisdiction, large cash, a dormant account reactivated, a sudden
// rise in velocity). Each template's defaults are the form's own (`PARAMETERS`), so a template and
// the form cannot disagree.
//
// `severity` says how urgent the template's alerts are: today a rule's alerts take their typology's
// default, which the Conduit applies (`services/api/alerts.py::TYPOLOGY_SEVERITY` and
// `DEFAULT_SEVERITY`); choosing a rule's own severity is the sentence builder's (stage (b)).
// `templates.test.ts` holds the two in step.
import type { QueuedAlert } from "../../../../packages/schemas/generated";

export type AlertSeverity = NonNullable<QueuedAlert["severity"]>;

export type TemplateTypology =
  | "structuring"
  | "rapid_movement"
  | "circular_flow"
  | "kyc_screening"
  | "shared_attributes"
  | "document_verification"
  | "pattern"
  | "high_risk_jurisdiction"
  | "large_cash"
  | "dormant_reactivated"
  | "velocity_rise";

export interface RuleTemplate {
  typology: TemplateTypology;
  name: string;
  group: "AML transaction monitoring" | "KYC" | "Any case";
  description: string;
  severity: AlertSeverity;
}

export const TEMPLATES: readonly RuleTemplate[] = [
  {
    typology: "structuring",
    name: "Structuring",
    group: "AML transaction monitoring",
    description: "Three or more payments, each under 10,000, adding up past it within 7 days.",
    severity: "medium",
  },
  {
    typology: "rapid_movement",
    name: "Rapid movement",
    group: "AML transaction monitoring",
    description: "80% or more of the money arriving leaves again within 48 hours.",
    severity: "medium",
  },
  {
    typology: "circular_flow",
    name: "Circular flow",
    group: "AML transaction monitoring",
    description: "Money back where it started in 4 movements or fewer, within 30 days.",
    severity: "medium",
  },
  {
    typology: "high_risk_jurisdiction",
    name: "High-risk jurisdiction",
    group: "AML transaction monitoring",
    description:
      "A payment to or from an account held in a jurisdiction on your list (the account's IBAN country code).",
    severity: "medium",
  },
  {
    typology: "large_cash",
    name: "Large cash",
    group: "AML transaction monitoring",
    description: "Cash paid in or drawn out of 10,000 or more in one movement.",
    severity: "medium",
  },
  {
    typology: "dormant_reactivated",
    name: "Dormant account reactivated",
    group: "AML transaction monitoring",
    description: "An account moving money again after 180 days or more without a movement.",
    severity: "medium",
  },
  {
    typology: "velocity_rise",
    name: "Sudden rise in velocity",
    group: "AML transaction monitoring",
    description:
      "An account's last 7 days at 3 times or more its own daily rate over the 90 days before, with 5 or more movements.",
    severity: "medium",
  },
  {
    typology: "kyc_screening",
    name: "Screening on onboarding",
    group: "KYC",
    description:
      "A new customer's name, and owners holding 25% or more, screened against the screening lists.",
    severity: "high",
  },
  {
    typology: "shared_attributes",
    name: "Shared contact details",
    group: "KYC",
    description: "A new customer's phone, email or IP address already used by 3 or more others.",
    severity: "low",
  },
  {
    typology: "document_verification",
    name: "Document verification",
    group: "KYC",
    description: "A new customer with no valid verifying document; checked again daily.",
    severity: "medium",
  },
  {
    typology: "pattern",
    name: "Drawn pattern",
    group: "Any case",
    description: "A pattern drawn and saved in the Query builder, matched after each load.",
    severity: "medium",
  },
];
