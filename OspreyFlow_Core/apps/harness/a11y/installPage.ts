// The guided install page's address and token for this directory's scans, shared by
// `playwright.config.ts` (which starts the page) and `install-page.spec.ts` (which presents the
// token as the page's cookie). Distinct from `keyboard/playwright.config.ts`'s 5192/7218, so both
// suites can run at once.
export const INSTALL_VITE_PORT = 5194;
export const INSTALL_API_PORT = "7220";
export const INSTALL_BASE = `http://localhost:${INSTALL_VITE_PORT}`;
export const INSTALL_TOKEN = "a11y-spec-install-token";
