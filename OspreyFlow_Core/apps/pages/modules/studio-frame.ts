// The Studio's enhancements (slice IS5a). Every one only saves a press: the page does its job with this script never
// loaded (a button submits each form), so nothing here is needed to use it. Plain TypeScript, no framework, no inline code.
//
//   the dataset select      changing it switches the dataset, as the React screen's select did
//   the folder input        choosing the folder reads it, as the React screen read it on change
//   the replace-my-draft box ticking it checks again at once, as the React screen did
//
// Each submits its own form as its own first button does (`requestSubmit` with that button as the submitter, so the button's
// name and value go too: the replace form's button says which step it is), so the form's own checks and its anti-forgery
// field are the page's own.

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
