// The deployment's brand (ADR-132): how every page of the deployment looks, set once in `osprey.yaml`
// (`appearance.brand`) and read from `/deployment.json` before anything is drawn. It is not the
// viewer's light or dark choice (`theme/theme.ts`): it never changes per viewer and is never kept
// in a cookie. Under `govuk` the page is light only, because the GOV.UK Design System has no dark
// mode, and the theme buttons are not drawn.
//
// Everything drawn by CSS follows `data-brand` on `<html>` (the brand block in `design/tokens.css`).
// The network's nine channels, the charts and the ramps are the same under every brand.
export type Brand = "ospreyflow" | "govuk";
export type Phase = "alpha" | "beta" | "live" | "none";

/** What `/deployment.json`'s `appearance` section says, read (`auth/oidcConfig.ts`). */
export interface Appearance {
  brand: Brand;
  serviceName: string | null;
  organisation: string | null;
  phase: Phase;
  /** ADR-132 Amendment 7: the deployment's own words for the banner, in place of "This is a new
   * service."; with no phase, shown alone. Absent when the deployment names none. */
  bannerText?: string;
}

export const PLAIN_APPEARANCE: Appearance = { brand: "ospreyflow", serviceName: null, organisation: null, phase: "none" };

const PHASES: readonly Phase[] = ["alpha", "beta", "live", "none"];

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

/** The `appearance` section of a deployment settings body. Anything it does not recognise falls
 * back to the OspreyFlow brand, so a malformed file never draws a GOV.UK page by accident. */
export function readAppearance(section: unknown): Appearance {
  if (typeof section !== "object" || section === null) return PLAIN_APPEARANCE;
  const given = section as Record<string, unknown>;
  const bannerText = text(given.banner_text);
  return {
    brand: given.brand === "govuk" ? "govuk" : "ospreyflow",
    serviceName: text(given.service_name),
    organisation: text(given.organisation),
    phase: PHASES.includes(given.phase as Phase) ? (given.phase as Phase) : "none",
    ...(bannerText ? { bannerText } : {}),
  };
}

/** Whether an address is on gov.uk (gov.uk itself or a name under it, such as `*.service.gov.uk`):
 * only there may a page carry the crown, Crown copyright and the Open Government Licence (ADR-132
 * Amendment 7, the owner's ruling of 13 November 2026). */
export function isGovUkHost(hostname: string): boolean {
  const name = hostname.toLowerCase().replace(/\.$/, "");
  return name === "gov.uk" || name.endsWith(".gov.uk");
}

/** `?brand=govuk` or `?brand=ospreyflow`, so a tester sees either brand without a redeploy. Only in
 * a development build: `dev` is `import.meta.env.DEV` at the one call site, never true in production. */
export function brandFromUrl(search: string, dev: boolean): Brand | null {
  if (!dev) return null;
  const asked = new URLSearchParams(search).get("brand");
  return asked === "govuk" || asked === "ospreyflow" ? asked : null;
}

/** The brand the page is showing now. */
export function currentBrand(): Brand {
  if (typeof document === "undefined") return "ospreyflow";
  return document.documentElement.getAttribute("data-brand") === "govuk" ? "govuk" : "ospreyflow";
}

/** Puts `brand` on the page. Call `applyTheme` after it: under `govuk` it holds the page light. */
export function applyBrand(brand: Brand): void {
  document.documentElement.setAttribute("data-brand", brand);
}

/** The page title: under `govuk` the GOV.UK form, "<service> – GOV.UK"; otherwise unchanged. */
export function brandTitle(appearance: Appearance, brand: Brand, current: string): string {
  if (brand !== "govuk") return current;
  return `${appearance.serviceName ?? appearance.organisation ?? "OspreyFlow"} – GOV.UK`;
}

/** Where `apps/workspace/scripts/sync_govuk_assets.mjs` puts GOV.UK Frontend's stylesheet, beside its fonts. */
export const GOVUK_STYLESHEET = "/assets/govuk/govuk-frontend.css";

/** Under `govuk`, adds GOV.UK Frontend's stylesheet to the page and resolves once it has loaded (or
 * failed, so a missing file never stops the Glass drawing). Under `ospreyflow` it fetches nothing. */
export function loadBrandStylesheet(brand: Brand, doc: Document = document): Promise<void> {
  if (brand !== "govuk") return Promise.resolve();
  return new Promise((resolve) => {
    const link = doc.createElement("link");
    link.rel = "stylesheet";
    link.href = GOVUK_STYLESHEET;
    link.onload = () => resolve();
    link.onerror = () => resolve();
    doc.head.append(link);
  });
}
