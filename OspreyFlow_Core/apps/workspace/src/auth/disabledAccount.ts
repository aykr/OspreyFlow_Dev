// ADR-148 Amendment 8: a person an administrator disabled in this deployment (Entra ID sign-in, where
// Entra still signs them in) is told so, and only when the Conduit says exactly that: its 401 carries
// `principal_auth`'s own words. Any other refusal keeps its own handling; none is read as this one.

/** `principal_auth`'s words for a person disabled in this deployment (`principal_from_claims`). */
export const CONDUIT_DISABLED_DETAIL = "this account is disabled in this deployment: ask an administrator";

/** What the sign-in screen says to them. */
export const DISABLED_ACCOUNT_WORDS = "Your account is disabled in this deployment. Ask an administrator.";

/** Whether a refusal is the Conduit saying this person is disabled here: a 401 whose `detail` is those
 * words exactly, never a guess from any other status, body or failure to read one. */
export async function isDisabledRefusal(refusal: Response): Promise<boolean> {
  if (refusal.status !== 401) return false;
  try {
    const body = (await refusal.json()) as { detail?: unknown };
    return body.detail === CONDUIT_DISABLED_DETAIL;
  } catch {
    return false;
  }
}
