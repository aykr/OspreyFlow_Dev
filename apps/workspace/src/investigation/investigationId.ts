// Investigation-id selection precedence on load — Stage 3a's own rehearsal finding, 23 September
// 2026: without a URL-param path, the Glass always created its own empty investigation on load,
// ignoring one already seeded via the API — an operator following `DEMO_GUIDE.md` saw an empty
// working set until they opened devtools and set `sessionStorage` by hand. `App.tsx` is the only
// caller; this lives in its own module (not inline in `App.tsx`) purely so it stays importable
// without pulling in Sigma/MapLibre and their own WebGL requirement — `App.tsx`'s top-level
// component tree needs a real browser/WebGL context even in tests, this precedence logic never
// does. `docs/02_GLASS_FRONTEND.md` is silent on load-time investigation-selection precedence
// (checked directly, not assumed) — recorded there as a proposal, not settled spec.
export const INVESTIGATION_ID_SESSION_KEY = "ospreyflow.investigationId";

export function investigationIdFromSession(): string | null {
  return sessionStorage.getItem(INVESTIGATION_ID_SESSION_KEY);
}

/** `?investigation=<id>` — takes precedence over `sessionStorage` so an operator who follows
 * `DEMO_GUIDE.md`'s seeded investigation link sees that investigation's data, not a stale one
 * left over in `sessionStorage` from an earlier session on the same browser tab. */
export function investigationIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("investigation");
}

/** `null` means "create one" — `App.tsx`'s own bootstrap effect still owns the `POST
 * /v1/investigations` fallback; this function only decides whether that fallback is needed. */
export function initialInvestigationId(): string | null {
  return investigationIdFromUrl() ?? investigationIdFromSession();
}
