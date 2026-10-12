/* The light and dark choice for OspreyFlow's pages that are not React (ADR-072): the launcher's
   welcome page and Keycloak's sign-in page. The Glass and the setup harness use
   apps/workspace/src/theme/theme.ts, which reads and writes the same cookie.

   The pages are on different names of one deployment (ADR-114 Amendment 4: the Glass at the base
   name, this sign-in page at id., the dashboards at bi.), so the choice is a cookie kept for the
   base name, which reaches all of them; apps/workspace/src/theme/theme.ts holds the same rule. It holds only "light" or "dark" and no server reads
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
    if (button) label(button, theme);
  }

  /* The button names the theme a press switches to: Light while the page is dark, Dark once it is
     light. */
  function label(button, theme) {
    var next = theme === "light" ? "dark" : "light";
    button.setAttribute("aria-label", "Switch to the " + next + " theme");
    button.title = "Switch to the " + next + " theme";
    button.textContent = next === "light" ? "\u2600 Light" : "\u263E Dark";
  }

  /* The base name the choice is kept for, or null for localhost or an address, where a browser takes
     no Domain and the choice is kept for the host alone. */
  function cookieDomain(hostname) {
    var host = String(hostname).toLowerCase().replace(/\.$/, "");
    if (host.indexOf(".") < 0 || /^[\d.]+$/.test(host) || host.indexOf(":") >= 0 || host.charAt(0) === "[") {
      return null;
    }
    return host.replace(/^(id|bi)\./, "");
  }

  /* The assignments that keep the choice: a copy kept for this host alone (as the page wrote it before
     the names) is cleared first, so it can never shadow the shared one. */
  function cookieWrites(theme, hostname) {
    var kept = NAME + "=" + theme + "; Path=/; Max-Age=31536000; SameSite=Lax";
    var domain = cookieDomain(hostname);
    return domain === null ? [kept] : [NAME + "=; Path=/; Max-Age=0", kept + "; Domain=" + domain];
  }

  function set(theme) {
    try {
      var writes = cookieWrites(theme, window.location.hostname);
      for (var i = 0; i < writes.length; i++) document.cookie = writes[i];
    } catch (e) {
      /* The page still changes; the choice just does not travel to the other pages. */
    }
    show(theme);
  }

  /* A button, drawn from the tokens, at the top right of the page, worded for the theme it switches to. */
  function mountButton(parent) {
    var existing = document.getElementById(BUTTON_ID);
    if (existing) return existing;
    var button = document.createElement("button");
    button.id = BUTTON_ID;
    button.type = "button";
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
  window.ospreyTheme = { current: current, set: set, mountButton: mountButton, cookieWrites: cookieWrites };

  if (document.body) {
    mountButton();
  } else {
    document.addEventListener("DOMContentLoaded", function () {
      mountButton();
    });
  }
})();
