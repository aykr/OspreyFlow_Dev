// The browser's half of what `cases.ts` (in `packages/glass-shared`) does for a case: the parts that
// touch this tab. Opening a case remembers it in the tab and reloads the page; removing one forgets it
// there. The requests themselves, and every word and label, are the package's, so a server-rendered page
// uses them without this file.
import { caseOpenUrl as caseUrl, removeCaseOnServer } from "@ospreyflow/glass-shared";
import { rememberCaseView } from "../views/lensHandoff";
import { INVESTIGATION_ID_SESSION_KEY } from "./investigationId";

/** Switching case reloads the page on purpose: the working set, the cross-filter store and the
 * delta stream are each built once per case, so a full navigation is the one way to be sure none
 * of the previous case's state is left behind. */
export function openCase(
  id: string,
  view?: "ingest" | "questions",
  navigate: (url: string) => void = (url) => window.location.assign(url),
): void {
  sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, id);
  navigate(caseUrl(id, view));
}

/** Opens a case on one of its views (ADR-144): the case is loaded as any switch loads it, and the
 * view is then opened over it as a lens. */
export function openCaseView(
  caseId: string,
  viewId: string,
  navigate: (url: string) => void = (url) => window.location.assign(url),
): void {
  sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, caseId);
  rememberCaseView(caseId, viewId);
  navigate(caseUrl(caseId, undefined, viewId));
}

/** A soft remove: the package's request, then this tab forgets the case if it was the one open. */
export async function removeCase(
  apiBaseUrl: string,
  bearerToken: string,
  id: string,
): Promise<void> {
  await removeCaseOnServer(apiBaseUrl, bearerToken, id);
  try {
    if (sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY) === id) {
      sessionStorage.removeItem(INVESTIGATION_ID_SESSION_KEY);
    }
  } catch {
    /* a convenience about this tab: never worth failing a removal over */
  }
}
