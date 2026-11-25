// The deployment's brand (ADR-132): how every page of the deployment looks, set once in `osprey.yaml`
// (`appearance.brand`) and read from `/deployment.json` before anything is drawn. It is not the
// viewer's light or dark choice (`theme/theme.ts`): it never changes per viewer and is never kept
// in a cookie. Under `govuk` the page is light only, because the GOV.UK Design System has no dark
// mode, and the theme buttons are not drawn.
//
// Everything drawn by CSS follows `data-brand` on `<html>` (the brand block in `packages/design/tokens.css`).
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
  /** ADR-152 decision 14, invariant I9: the GOV.UK identity switch (`appearance.govuk_identity`, off by default). Under
   * `govuk` with it off no page shows the crown, the GOV.UK logotype or the GOV.UK typeface; the header carries the
   * organisation's name and the type is the fallback stack. Means nothing under `ospreyflow`. */
  govukIdentity: boolean;
}

export const PLAIN_APPEARANCE: Appearance = {
  brand: "ospreyflow",
  serviceName: null,
  organisation: null,
  phase: "none",
  govukIdentity: false,
};

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
    // Only a real `true`: a string, a number or an absent key is off, so a malformed file never turns the identity on.
    govukIdentity: given.govuk_identity === true,
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

/** `?govuk_identity=on` or `?govuk_identity=off`, so a tester sees the GOV.UK look either way without a redeploy. Only
 * in a development build, as `brandFromUrl`. */
export function identityFromUrl(search: string, dev: boolean): boolean | null {
  if (!dev) return null;
  const asked = new URLSearchParams(search).get("govuk_identity");
  return asked === "on" ? true : asked === "off" ? false : null;
}

/** Whether the page is showing the GOV.UK identity now: under `govuk`, with the switch on. The CSS follows
 * `data-govuk-identity` on `<html>` (`packages/design/tokens.css`), which is set only then. */
export function currentGovukIdentity(): boolean {
  if (typeof document === "undefined") return false;
  const root = document.documentElement;
  return root.getAttribute("data-brand") === "govuk" && root.getAttribute("data-govuk-identity") === "on";
}

/** Whether the page is drawing the GOV.UK typeface now: under `govuk`, with the switch on, on a gov.uk address. GDS
 * Transport is licensed for services on GOV.UK domains only (`packages/design/fonts.json`: `only_when`, `only_on`), so
 * both conditions are in the page's own markers: the CSS names the face only under `data-govuk-typeface="on"`. */
export function currentGovukTypeface(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.getAttribute("data-govuk-typeface") === "on" && currentGovukIdentity();
}

/** Puts `brand` on the page, and the GOV.UK identity switch with it: `govukIdentity` counts only under `govuk` (it means
 * nothing under `ospreyflow`), and the attribute is absent otherwise. `data-govuk-typeface` is the switch **and** a
 * gov.uk address (`hostname`: the page's own), so with the switch on at any other address the page draws no GDS
 * Transport (ADR-152 Amendment 2 item 3). Call `applyTheme` after it: under `govuk` it holds the page light. */
export function applyBrand(
  brand: Brand,
  govukIdentity = false,
  hostname = typeof window === "undefined" ? "" : window.location.hostname,
): void {
  const root = document.documentElement;
  root.setAttribute("data-brand", brand);
  const identity = brand === "govuk" && govukIdentity;
  if (identity) root.setAttribute("data-govuk-identity", "on");
  else root.removeAttribute("data-govuk-identity");
  if (identity && isGovUkHost(hostname)) root.setAttribute("data-govuk-typeface", "on");
  else root.removeAttribute("data-govuk-typeface");
}

/** The page title: under `govuk` the GOV.UK form, "<service> – GOV.UK"; otherwise unchanged. */
export function brandTitle(appearance: Appearance, brand: Brand, current: string): string {
  if (brand !== "govuk") return current;
  return `${appearance.serviceName ?? appearance.organisation ?? "OspreyFlow"} – GOV.UK`;
}

/** Where `apps/workspace/scripts/sync_govuk_assets.mjs` puts GOV.UK Frontend's stylesheet. With the identity switch off
 * it is the stylesheet without the face's rules or the crest, and no fonts stand beside it; on, the fonts do. */
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
