// Sign-in keyboard harness — the eighth keyboard-driven surface (`actionRegistry.ts`'s own
// `SIGN_IN_ACTIONS` docstring has the reasoning for a separate harness/spec pair). Renders the real
// `SignInScreen` wired to the real `signIn()` from `src/auth/userManager.ts` — not a stub — so
// `sign-in.spec.ts` proves a real `oidc-client-ts` OIDC-discovery fetch and a real top-level
// navigation to the identity provider's authorization endpoint, intercepted at the transport (the
// network layer), the same "real call, mocked at the transport" shape `metrics-panel-harness.tsx`'s
// own docstring already establishes for a `fetch`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import { applyHarnessBrand } from "./brandHarness";
import "../src/design/primitives.css";
import { SignInScreen } from "../src/auth/SignInScreen";
import { BrandFrame } from "../src/brand/BrandFrame";
import { signIn } from "../src/auth/userManager";

// ADR-115 E2: `?organisation=<alias>` stands for a deployment naming a brokered provider.
const organisation = new URLSearchParams(location.search).get("organisation");

function Harness() {
  return (
    <SignInScreen
      reason={null}
      marking="OFFICIAL"
      welcome={{ organisationSignIn: organisation, about: true, links: {}, version: "c01833b" }}
      onSignIn={(organisationProvider) => void signIn(organisationProvider)}
    />
  );
}

const brand = await applyHarnessBrand();

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// Under `?brand=govuk` the page sits in the real GOV.UK frame, as the Glass draws it (ADR-132).
createRoot(container).render(
  brand === "govuk" ? (
    <BrandFrame appearance={{ brand: "govuk", serviceName: "Prison Intelligence", organisation: "Ministry of Examples", phase: "beta" }}>
      <Harness />
    </BrandFrame>
  ) : (
    <Harness />
  ),
);
