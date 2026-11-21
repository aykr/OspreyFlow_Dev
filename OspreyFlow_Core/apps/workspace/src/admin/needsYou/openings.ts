// The Glass's binding of the *Needs you* requests to the tab: they are kept in the session's storage, since
// opening the Studio on another case reloads the page (`openCase`). The requests themselves, and the waiting,
// taking and listening, are the package's (`packages/glass-shared/src/admin/needsYou/openings.ts`).
import { bindOpeningsStorage } from "@ospreyflow/glass-shared";

export { onOpening, peekOpening, requestOpening, takeOpening, type Opening } from "@ospreyflow/glass-shared";

bindOpeningsStorage(() => sessionStorage);
