// Which view to open over a case once it has loaded (ADR-144): `case_view` in the address, which a
// view chosen in another case's row navigates to, kept in `sessionStorage` for the sign-in round
// trip, which drops the query. It grants nothing: the view is then asked for from the Conduit like
// any other, which answers only with a view this reader may see.
const KEY = "ospreyflow.caseView";

/** Notes that `viewId` is to be opened over `caseId` when it loads. */
export function rememberCaseView(caseId: string, viewId: string, storage: Storage = sessionStorage): void {
  try {
    storage.setItem(KEY, JSON.stringify({ caseId, viewId }));
  } catch {
    /* a preference about a screen: the case still opens, without the view */
  }
}

/** The view to open over `caseId`, from the address or the note, once; the note is then cleared. */
export function takeCaseView(caseId: string, search: string, storage: Storage = sessionStorage): string | null {
  const fromUrl = new URLSearchParams(search).get("case_view");
  let noted: string | null = null;
  try {
    const raw = storage.getItem(KEY);
    storage.removeItem(KEY);
    const value = raw ? (JSON.parse(raw) as { caseId?: unknown; viewId?: unknown }) : null;
    if (value && value.caseId === caseId && typeof value.viewId === "string") noted = value.viewId;
  } catch {
    noted = null;
  }
  return fromUrl || noted;
}
