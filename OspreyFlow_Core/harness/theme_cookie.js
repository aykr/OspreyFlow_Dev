/* The light and dark choice for OspreyFlow's pages that are not React (ADR-072): the launcher's
   welcome page and Keycloak's sign-in page. The Glass and the setup harness use
   apps/workspace/src/theme/theme.ts, which reads and writes the same cookie.

   The pages are on different ports of one host. A browser keeps a page's storage per port but a
   cookie per host, so the choice is a cookie. It holds only "light" or "dark" and no server reads
   it. Dark is the default. Written in plain ES5 with no dependency, since it is put in a page
   as it is. Colours come only from the design tokens (var(--...)), which every one of these pages
   already has. */
(function () {
  var NAME = "ospreyflow_theme";
  var BUTTON_ID = "osprey-theme-toggle";
  var root = document.documentElement;

  function read() {
    try {
      var match = document.cookie.match(new RegExp("(?:^|;\\s*)" + NAME + "=([^;]*)"));
      return match && (match[1] === "light" || match[1] === "dark") ? match[1] : null;
    } catch (e) {
      return null;
    }
  }

  function current() {
    return root.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function show(theme) {
    root.setAttribute("data-theme", theme);
    var button = document.getElementById(BUTTON_ID);
    if (button) {
      button.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
      button.style.borderColor = theme === "light" ? "var(--brass)" : "var(--border)";
      button.style.color = theme === "light" ? "var(--brass)" : "var(--text-primary)";
    }
  }

  function set(theme) {
    try {
      document.cookie = NAME + "=" + theme + "; Path=/; Max-Age=31536000; SameSite=Lax";
    } catch (e) {
      /* The page still changes; the choice just does not travel to the other pages. */
    }
    show(theme);
  }

  /* A Light button, drawn from the tokens, at the top right of the page. Pressed means light. */
  function mountButton(parent) {
    var existing = document.getElementById(BUTTON_ID);
    if (existing) return existing;
    var button = document.createElement("button");
    button.id = BUTTON_ID;
    button.type = "button";
    button.setAttribute("aria-label", "Light theme");
    button.setAttribute("aria-pressed", "false");
    button.title = "Switch between the light and dark theme";
    button.textContent = "☀ Light";
    button.setAttribute(
      "style",
      "position: fixed; top: var(--sp-12); right: var(--sp-12); z-index: 1000;" +
        " padding: var(--sp-6) var(--sp-12); border: 1px solid var(--border);" +
        " border-radius: var(--r-control); background: var(--surface-raised);" +
        " color: var(--text-primary); font: inherit; font-size: var(--fs-13); cursor: pointer;"
    );
    button.addEventListener("click", function () {
      set(current() === "light" ? "dark" : "light");
    });
    (parent || document.body).appendChild(button);
    show(current());
    return button;
  }

  show(read() || "dark");
  window.ospreyTheme = { current: current, set: set, mountButton: mountButton };

  if (document.body) {
    mountButton();
  } else {
    document.addEventListener("DOMContentLoaded", function () {
      mountButton();
    });
  }
})();
