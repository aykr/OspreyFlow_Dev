/* The sign-in card's behaviour on Keycloak's own pages (ADR-115, Phase E stage E2).
 *
 * The Glass never takes a password (ADR-115 decision 4), so the handoff's email-or-username form is
 * Keycloak's, and this script gives it the handoff's behaviour: validation on submit, never on
 * keystroke, in the handoff's own words, each field in error marked for assistive technology; the
 * reset page's button saying what it sends; "Check your email" after a reset is sent; and, where the
 * deployment has no mail server, the way back named where the reset link would be (decision 6).
 *
 * Written against Keycloak 26.0.8's `keycloak.v2` markup, measured: `#kc-form-login` with
 * `#username`, `#password`; `#kc-reset-password-form` with `#username`; `#kc-page-title`.
 * `window.OSPREY_RESET_BY_EMAIL` is written before this file by `harness/keycloak_theme.py`.
 */
(function () {
  "use strict";

  var SAY = {
    emptyIdentifier: "Enter your email address or username.",
    badAddress: "Enter an email address in the format name@organisation.gov.uk, or use your username.",
    badUsername: "Usernames use letters, numbers, dots, hyphens and underscores, with no spaces.",
    emptyPassword: "Enter your password.",
    noReset:
      "Forgot your password? Ask your OspreyFlow administrator to reset your sign-in. They'll give you a one-time code.",
    foot: "No account yet? Your OspreyFlow administrator invites people and assigns roles.",
    sendReset: "Send reset link",
    checkEmail: "Check your email",
    signIn: "Sign in",
    back: "Back to sign in",
    sentStarts: "If an OspreyFlow account matches",
  };

  function identifierProblem(value) {
    var v = value.trim();
    if (!v) return SAY.emptyIdentifier;
    if (v.indexOf("@") !== -1) return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v) ? null : SAY.badAddress;
    return /^[A-Za-z0-9._-]{2,64}$/.test(v) ? null : SAY.badUsername;
  }

  function clearErrors(form) {
    var shown = form.querySelectorAll(".osprey-field-error");
    for (var i = 0; i < shown.length; i++) shown[i].parentNode.removeChild(shown[i]);
    var marked = form.querySelectorAll("[aria-invalid]");
    for (var j = 0; j < marked.length; j++) {
      marked[j].removeAttribute("aria-invalid");
      marked[j].removeAttribute("aria-describedby");
    }
  }

  function showError(field, message) {
    var id = field.id + "-osprey-error";
    var said = document.createElement("span");
    said.id = id;
    said.className = "osprey-field-error";
    said.textContent = message;
    // Directly under the field's own box (the password's box and its show button are one group),
    // before any help that follows it.
    var box = field.closest(".pf-v5-c-input-group") || field.closest(".pf-v5-c-form-control") || field;
    box.parentNode.insertBefore(said, box.nextSibling);
    field.setAttribute("aria-invalid", "true");
    field.setAttribute("aria-describedby", id);
  }

  function guard(form, checks) {
    form.noValidate = true;
    form.addEventListener("submit", function (event) {
      clearErrors(form);
      var first = null;
      for (var i = 0; i < checks.length; i++) {
        var field = form.querySelector("#" + checks[i].id);
        if (!field) continue;
        var problem = checks[i].problem(field.value);
        if (problem) {
          showError(field, problem);
          first = first || field;
        }
      }
      if (first) {
        event.preventDefault();
        // Keycloak's own `onsubmit` has already disabled its button (measured on 26.0.8); a refused
        // submit gives it back, or the corrected form could not be sent.
        var buttons = form.querySelectorAll("[type=submit]");
        for (var b = 0; b < buttons.length; b++) buttons[b].disabled = false;
        if (first.focus) first.focus();
      }
    });
  }

  function addAfter(form, className, text) {
    var line = document.createElement("p");
    line.className = className;
    line.textContent = text;
    form.parentNode.insertBefore(line, form.nextSibling);
    return line;
  }

  function sentAlert() {
    var alerts = document.querySelectorAll(".pf-v5-c-alert.pf-m-success, .alert-success");
    for (var i = 0; i < alerts.length; i++) {
      if (alerts[i].textContent.trim().indexOf(SAY.sentStarts) === 0) return alerts[i];
    }
    return null;
  }

  function start() {
    var login = document.getElementById("kc-form-login");
    var reset = document.getElementById("kc-reset-password-form");
    var title = document.getElementById("kc-page-title");

    if (login) {
      guard(login, [
        { id: "username", problem: identifierProblem },
        { id: "password", problem: function (v) { return v ? null : SAY.emptyPassword; } },
      ]);
      if (!window.OSPREY_RESET_BY_EMAIL) {
        var password = login.querySelector("#password");
        var group = password && (password.closest(".pf-v5-c-form__group") || password.parentNode);
        if (group) {
          var help = document.createElement("p");
          help.className = "osprey-no-reset";
          help.textContent = SAY.noReset;
          group.appendChild(help);
        }
      }
      addAfter(login, "osprey-card-foot", SAY.foot);

      if (sentAlert() && title) {
        login.hidden = true;
        title.textContent = SAY.checkEmail;
        var back = document.createElement("button");
        back.type = "button";
        back.className = "pf-v5-c-button pf-m-secondary osprey-back";
        back.textContent = SAY.back;
        back.addEventListener("click", function () {
          login.hidden = false;
          title.textContent = SAY.signIn;
          var alert = sentAlert();
          if (alert) alert.hidden = true;
          back.parentNode.removeChild(back);
        });
        login.parentNode.insertBefore(back, login);
      }
    }

    if (reset) {
      // Keycloak puts the instruction after the form; the handoff's card has it under the title.
      var info = document.getElementById("kc-info");
      if (info) {
        info.classList.add("osprey-lead");
        reset.parentNode.insertBefore(info, reset);
      }
      guard(reset, [{ id: "username", problem: identifierProblem }]);
      var submit = reset.querySelector("[type=submit]");
      if (submit) {
        if (submit.tagName === "INPUT") submit.value = SAY.sendReset;
        else submit.textContent = SAY.sendReset;
      }
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
