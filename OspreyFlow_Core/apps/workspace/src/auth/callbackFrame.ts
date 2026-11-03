// `06_DECISIONS.md` ADR-050 Amendment 1. The silent renewal is ADR-050's own `prompt=none` round
// against the identity provider's session cookie, run by `oidc-client-ts` in a hidden iframe; the
// sign-in again after a session has ended runs in a small window of its own. Both are sent back by the
// identity provider to the workspace's own address (`redirect_uri`, the one address the realm
// registers), so the page that loads there is a whole workspace unless it notices it is only carrying
// an answer. This notices, and hands the answer to the window that asked in the shape
// `oidc-client-ts` listens for (its `IFrameWindow.notifyParent` / `PopupWindow.notifyOpener`), to the
// workspace's own origin only.
//
// Told apart without reading the library's stored state: the iframe is the only way the workspace is
// ever framed, and the sign-in window is opened under a name of its own (`SIGN_IN_WINDOW_NAME`), so a
// workspace a launcher opened in a new tab (which also has an opener) completes its own sign-in.

/** The name the sign-in window is opened under (`popupWindowTarget`). Kept across its visits to the
 * identity provider: they are on the same site, so the browser does not clear it. */
export const SIGN_IN_WINDOW_NAME = "osprey-sign-in-again";

function carriesAnAnswer(search: string): boolean {
  const params = new URLSearchParams(search);
  return params.has("state") && (params.has("code") || params.has("error"));
}

/** True when this page only carried an answer and has handed it on: draw nothing. */
export function answerTheWindowThatAsked(win: Window = window): boolean {
  if (!carriesAnAnswer(win.location.search)) return false;
  const framed = win.parent !== null && win.parent !== win;
  const target = framed ? win.parent : win.name === SIGN_IN_WINDOW_NAME ? win.opener : null;
  if (!target) return false;
  (target as Window).postMessage(
    { source: "oidc-client", url: win.location.href, keepOpen: false },
    win.location.origin,
  );
  return true;
}
