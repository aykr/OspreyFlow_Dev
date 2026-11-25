// Harness pages do not run `src/main.tsx`, so `?brand=govuk` is applied here instead (ADR-132). With
// no `?brand=` it leaves a page exactly as before: it sets `data-brand="ospreyflow"`, which nothing
// styles. The GOV.UK identity (ADR-152 decision 14) is on here unless `?govuk_identity=off`: the specs measure the GOV.UK
// look with its typeface. Two things make that so: the Playwright servers' sync step copies the font files
// (`OSPREY_GOVUK_IDENTITY=1` in each config), and the helper below hands `applyBrand` a gov.uk address, because the
// face is drawn only with the identity on AND on a gov.uk address (`only_on: gov.uk`) and a Playwright server answers
// on localhost. The address is this helper's argument only: no request, setting or shipped build sees it.
// Not a spec file: harnesses import this, never a `*.spec.ts`.
import { applyBrand, brandFromUrl, identityFromUrl, loadBrandStylesheet, applyTheme } from "@ospreyflow/glass-shared";

/** The gov.uk name the harness presents to `applyBrand` in place of the server's own (`localhost`). */
export const HARNESS_GOVUK_HOST = "harness.service.gov.uk";

export async function applyHarnessBrand(): Promise<"govuk" | "ospreyflow"> {
  const brand = brandFromUrl(window.location.search, true) ?? "ospreyflow";
  applyBrand(brand, identityFromUrl(window.location.search, true) ?? true, HARNESS_GOVUK_HOST);
  if (brand === "govuk") applyTheme("light");
  await loadBrandStylesheet(brand);
  return brand;
}
