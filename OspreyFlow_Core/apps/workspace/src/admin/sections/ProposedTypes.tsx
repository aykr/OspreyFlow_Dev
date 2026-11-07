// Admin › Data › Proposed types (ADR-090 Amendment 5, ADR-145 decision 1; under Data by the
// orchestrator's settlement of 7 November 2026). Behind `manage_ontology` and the administrator role.
import { useState } from "react";

import { Button } from "../../design/primitives";
import { ProposedTypes } from "../../linktypes/ProposedTypes";
import type { AdminApi } from "../api";

/** ADR-145 decision 1: *Proposed types* left the Glass's rail. Until the Studio's Model tab decides
 * them (A2, ADR-143) they are decided here, behind the same right (`manage_ontology`). */
export function ProposedTypesSection({ api }: { api: AdminApi }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <p className="label">The relationship types analysts of your unit proposed, each to promote, reject or retire.</p>
      <div>
        <Button aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
          Review proposed types
        </Button>
      </div>
      <ProposedTypes apiBaseUrl={api.apiBaseUrl} bearerToken={api.bearerToken} open={open} onClose={() => setOpen(false)} />
    </>
  );
}
