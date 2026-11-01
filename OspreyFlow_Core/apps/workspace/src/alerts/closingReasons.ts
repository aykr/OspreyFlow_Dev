// ADR-133 decision 7's closed list of closing reasons, as the owner named it on 1 November 2026, in
// the order the close dialog offers them. The values are the Conduit's (`schemas.domain.
// CLOSING_REASONS`); the Conduit refuses any other in words. Only a true match confirms what the alert
// found (rule 5); every other reason leaves it a suggestion.
import type { AlertDispositionInput } from "../../../../packages/schemas/generated";

export type ClosingReason = AlertDispositionInput["disposition"];

export const CLOSING_REASONS: Record<ClosingReason, string> = {
  true_positive: "True match",
  false_positive: "False positive",
  duplicate: "Duplicate",
  no_further_action: "No further action",
  referred: "Referred",
};

/** A closing reason as it is said: "True match"; an unknown value as itself, never hidden. */
export function closingReasonLabel(reason: string | null | undefined): string {
  return reason ? (CLOSING_REASONS[reason as ClosingReason] ?? reason) : "";
}
