// `06_DECISIONS.md` ADR-050 — the sign-in screen. Shown whenever there is no valid token
// (`docs/02_GLASS_FRONTEND.md` §2's own "unauthenticated load" case) and, per ADR-050's amendment
// of objection 7, this is the surface the tests-owed list's "Glass's reaction to a 401" actually
// tests — not the Conduit's already-covered refusal, but that this screen, specifically, is what
// an unauthenticated or refused caller sees.
import { Button } from "../design/primitives/Button";

export interface SignInScreenProps {
  /** `00_ARCHITECTURE.md` §1.3's own distinction, carried to the Glass: *cannot reach the identity
   * provider* is a different statement from *the identity provider said no*, and a wrong-audience
   * token refused by the Conduit is a third — telling an analyst the wrong one of these is a false
   * and alarming statement about their own access. `null` means neither has happened yet (a plain,
   * first, unauthenticated load). */
  reason?: string | null;
  onSignIn: () => void;
}

export function SignInScreen({ reason, onSignIn }: SignInScreenProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        gap: "var(--sp-16)",
        padding: "var(--sp-24)",
        textAlign: "center",
      }}
    >
      <h1 style={{ margin: 0 }}>OspreyFlow</h1>
      <p style={{ color: "var(--text-secondary)", maxWidth: 420 }}>
        Sign in with your analyst credentials to open the workspace. Credentials are entered at
        your organisation's identity provider — never here.
      </p>
      {reason && (
        <p role="alert" style={{ color: "var(--error)", maxWidth: 420 }}>
          {reason}
        </p>
      )}
      <Button variant="primary" onClick={onSignIn}>
        Sign in
      </Button>
    </div>
  );
}
