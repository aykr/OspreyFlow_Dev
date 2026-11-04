// The page frame around the Glass (ADR-132). Top to bottom: the skip link, the GOV.UK header (GOV.UK
// brand only), the phase banner (either brand, when the deployment is in alpha or beta), the Glass
// itself in `#main-content` (the skip link's target), and the GOV.UK footer (GOV.UK brand only).
// Under the OspreyFlow brand with no phase only the skip link is added, and it is out of the page's
// flow until it has focus, so the Glass is laid out exactly as before.
//
// No service-name band stands under the GOV.UK header (ADR-132 Amendment 5, the owner's ruling of
// 4 November 2026: it took too much of the workspace's height). The frame names the service in the
// page title instead, "<service> – GOV.UK", so the name is still on every page.
//
// The workspace and the Admin area fill the window (`--workspace-height`, default `100vh`). When
// something stands above them, the frame measures it and sets that height to what is left, so the
// status bar stays in view; the footer is below, reached by scrolling, as on any GOV.UK page.
import { useLayoutEffect, useRef, type ReactNode } from "react";

import { brandTitle, type Appearance } from "./brand";
import { GovukFooter } from "./govuk/GovukFooter";
import { GovukHeader } from "./govuk/GovukHeader";
import { PhaseBanner } from "./govuk/PhaseBanner";
import { SkipLink } from "./govuk/SkipLink";

export const MAIN_CONTENT_ID = "main-content";

export function BrandFrame({ appearance, children }: { appearance: Appearance; children: ReactNode }) {
  const above = useRef<HTMLDivElement>(null);

  // Under GOV.UK the page title is "<service> – GOV.UK"; under OspreyFlow it is left as it is.
  useLayoutEffect(() => {
    document.title = brandTitle(appearance, appearance.brand, document.title);
  }, [appearance]);

  useLayoutEffect(() => {
    const element = above.current;
    if (!element) return;
    const root = document.documentElement;
    const fit = () => {
      const height = element.offsetHeight;
      if (height > 0) root.style.setProperty("--workspace-height", `calc(100vh - ${height}px)`);
      else root.style.removeProperty("--workspace-height");
    };
    fit();
    // jsdom has no ResizeObserver; a browser re-measures when the header wraps or the window narrows.
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    observer?.observe(element);
    return () => {
      observer?.disconnect();
      root.style.removeProperty("--workspace-height");
    };
  }, []);

  return (
    <>
      <SkipLink target={MAIN_CONTENT_ID} />
      <div ref={above}>
        <GovukHeader />
        <PhaseBanner phase={appearance.phase} />
      </div>
      {/* Focused by the skip link; not itself a control, so it is not in the Tab order. */}
      <div id={MAIN_CONTENT_ID} tabIndex={-1} className="main-content">
        {children}
      </div>
      <GovukFooter organisation={appearance.organisation} />
    </>
  );
}
