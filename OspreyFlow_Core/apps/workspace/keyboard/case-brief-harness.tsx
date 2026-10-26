// Case brief keyboard harness (ADR-128 decision 3): the Brief section of the Cases drawer, as App
// renders it, with no rights known (so every edit a case's Author may make is offered). The spec
// intercepts the routes and plays the server, the case's level included; the attachments the section
// was asked to open are on `window.__CASE_BRIEF__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { CaseBrief } from "../src/investigation/CaseBrief";

declare global {
  interface Window {
    __CASE_BRIEF__?: { opened: { kind: string; id: string }[] };
  }
}

window.__CASE_BRIEF__ = { opened: [] };

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <CaseBrief
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="c1"
    onOpenAttachment={(kind, id) => {
      window.__CASE_BRIEF__!.opened.push({ kind, id });
    }}
  />,
);
