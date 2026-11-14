// A sign-in refused with words the person can act on (ADR-148 Amendments 15, 17 and 18): the Conduit's 401
// carries a stable tag beside them (`error`), and the sign-in page shows those words, the Conduit's own.
// Every other refusal keeps the general words; none is shown from a guess at an untagged `detail`.

/** The tags whose `detail` the sign-in page shows (`principal_auth`'s `PrincipalResolutionError.error`). */
export const ACTIONABLE_REFUSALS: readonly string[] = ["access_not_set", "token_version", "guest_not_admitted"];

/** The Conduit's words for a refusal tagged as one the person can act on, or null for any other answer:
 * another status, another or no tag, no words, or a body that cannot be read. Reads a copy, so the
 * refusal's own body is still there for whatever reads it next. */
export async function actionableRefusalWords(refusal: Response): Promise<string | null> {
  if (refusal.status !== 401) return null;
  try {
    const body = (await refusal.clone().json()) as { detail?: unknown; error?: unknown };
    if (typeof body.error !== "string" || !ACTIONABLE_REFUSALS.includes(body.error)) return null;
    return typeof body.detail === "string" && body.detail.trim() !== "" ? body.detail : null;
  } catch {
    return null;
  }
}
