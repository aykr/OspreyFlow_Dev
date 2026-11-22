// The Studio's enhancements (slice IS5a). Every one only saves a press: the page does its job with this script never
// loaded (a button submits each form), so nothing here is needed to use it. Plain TypeScript, no framework, no inline code.
//
//   the dataset select      changing it switches the dataset, as the React screen's select did
//   the folder input        choosing the folder reads it, as the React screen read it on change
//   the replace-my-draft box ticking it checks again at once, as the React screen did
//   a link to Model         following it asks the workspace to open on Model, as the Needs-you jump does
//
// Each submits its own form as its own first button does (`requestSubmit` with that button as the submitter, so the button's
// name and value go too: the replace form's button says which step it is), so the form's own checks and its anti-forgery
// field are the page's own.

// (A module with nothing exported: it only wires the page it is loaded in.)
export {};

function submitOnChange(selector: string): void {
  for (const control of Array.from(document.querySelectorAll<HTMLInputElement | HTMLSelectElement>(selector))) {
    control.addEventListener("change", () => {
      // A folder input with nothing chosen is not a request.
      if (control instanceof HTMLInputElement && control.type === "file" && (control.files?.length ?? 0) === 0) return;
      const form = control.form;
      if (form) form.requestSubmit(form.querySelector<HTMLButtonElement>("button[type='submit']"));
    });
  }
}

submitOnChange("#studio-switch select[name='dataset']");
submitOnChange("input[type='file'][name='folder']");
submitOnChange("#studio-replace input[name='replace']");

// A link to the Model place asks the workspace to open on it. Model is not on the pages yet, so the link opens the Studio in
// the workspace, which opens on Pipelines unless it has been asked for Model: it reads that request from the tab's own
// storage, where the React screen's Needs-you jump writes it (`packages/glass-shared/src/admin/needsYou/openings.ts`: the
// same key, the same shape, one request of each kind). The link goes on being followed whatever the storage does; with this
// script never loaded the workspace opens on its own first place, and the page says so.
const OPENING_KEY = "osprey.needsYou.opening";

function askForModel(datasetId: string): void {
  try {
    const raw = sessionStorage.getItem(OPENING_KEY);
    const waiting: { kind?: string }[] = raw ? (JSON.parse(raw) as { kind?: string }[]) : [];
    const kept = Array.isArray(waiting) ? waiting.filter((w) => w.kind !== "studio") : [];
    sessionStorage.setItem(OPENING_KEY, JSON.stringify([...kept, { kind: "studio", tab: "model", datasetId }]));
  } catch {
    // No session storage: the Studio opens on its first place.
  }
}

for (const link of Array.from(document.querySelectorAll<HTMLAnchorElement>("a[data-opens-model]"))) {
  link.addEventListener("click", () => {
    const datasetId = link.getAttribute("data-opens-model");
    if (datasetId) askForModel(datasetId);
  });
}
