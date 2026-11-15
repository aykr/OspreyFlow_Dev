# Admin › Models key handling: the owner's independent review, 15 November 2026

The owner's note, verbatim as received, is the brief for the platform lane's admin-forms slice (v0.6.1; nothing of it
touches v0.6.0). Branch `lane/platform-admin-forms`, reviewed at `9f6b2c6`.

Asked for, in summary (the full findings, line numbers and reasons are in the owner's message, relayed to platform the
same day):
- **Fix A (medium):** a key pasted into a model-name box can be echoed and audited. (1) `engine_checked`'s audit records
  each job and its outcome, not the typed model name; (2) a model name is accepted only if it matches what model names
  look like, shown against every catalogue name and example; (3) answer: stop echoing a refused model name, by job.
- **Fix B (low):** the Edit route's 422 echoes field names; answer `extra_forbidden`, `json_invalid` and no-`loc` errors
  in fixed words, as `_check_refusal` does.
- **Fix C (low):** `redacted()` is exact-match; fixed words per field, or prove no validator quotes its input.
- **Fix D (low):** confirm nothing reports local variables with an error, and plant it (P3).
- **Plants P1-P9**, each red first, recorded beside `plants_run.txt` and `red-first.txt`: odd-shaped keys in a model-name
  box (P1) and as the real key (P2); a non-httpx error mid-check (P3); full log-record capture (P4); every file in the
  temp folder (P5); `services.api.model_keys` commands (P6); `ospreyflow models key`'s output and exec argv (P7);
  Playwright storage and URLs (P8); a key as a non-string or in a query string (P9).
- **Four answers in writing:** (1) is the key removed from `deployment.env` after `move_keys`, where, and which test
  proves it; (2) on the real LiteLLM, does a credential body reach its logs and is it encrypted in its database, shown
  by one measured run with a synthetic key; (3) what removes a credential left by a Conduit killed between
  `put_credential` and the save; (4) does the guide prefer the hidden prompt and warn about shell history.
- **Back:** a table of each fix and plant with its commit; the four answers with file and line or a measurement;
  disagreements said plainly before building; no change to v0.6.0.
