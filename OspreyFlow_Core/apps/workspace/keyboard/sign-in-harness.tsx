// Sign-in keyboard harness — the eighth keyboard-driven surface (`actionRegistry.ts`'s own
// `SIGN_IN_ACTIONS` docstring has the reasoning for a separate harness/spec pair). Renders the real
// `SignInScreen` wired to the real `signIn()` from `src/auth/userManager.ts` — not a stub — so
// `sign-in.spec.ts` proves a real `oidc-client-ts` OIDC-discovery fetch and a real top-level
// navigation to the identity provider's authorization endpoint, intercepted at the transport (the
// network layer), the same "real call, mocked at the transport" shape `metrics-panel-harness.tsx`'s
// own docstring already establishes for a `fetch`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { SignInScreen } from "../src/auth/SignInScreen";
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

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);
