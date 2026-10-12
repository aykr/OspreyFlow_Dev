.PHONY: check lint typecheck trivy trivy-image-ingest trivy-image-api trivy-image-workspace trivy-image-harness test-js launch refresh seed-paysim seed-hmp seed-fixture-corp seed-ledger register-sign-in dev-up dev-down docker-clean glass-perf glass-a11y glass-keyboard glass-map-verify glass-live harness-keyboard harness-a11y

PY := .venv/bin/python
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy

# What runs from this folder alone (`06_DECISIONS.md` ADR-114 Amendment 2). The specification's own
# gates and the test suites are the developer repository's, in its Makefile; its `ci` runs this
# `check` first. A user of this repository needs nothing from it.
check: lint typecheck trivy trivy-image-ingest trivy-image-api trivy-image-workspace trivy-image-harness harness-a11y

lint:
	$(RUFF) check .
	npm run lint

typecheck:
# `harness` joined this target on 24 September 2026 (ADR-049 Stage 2 §3/§4): seven real errors, every
# one an untyped `dict`/`list` crossing a boundary the harness passes compose documents across.
	$(MYPY) packages services harness
	npm run typecheck

# The Glass's and the harness's unit tests.
test-js:
	npm test --workspace apps/workspace
	npm test --workspace apps/harness

trivy:
	trivy fs --exit-code 1 --severity HIGH,CRITICAL --include-dev-deps --skip-dirs node_modules,.venv .

# `trivy image` per service, added in the phase that gives it a Dockerfile
# (process/07_BUILD_PLAN.md, "Standing rules for the whole build") — not
# batched into Phase 8. `--ignore-unfixed`: unlike the fs scan above, an
# image scan turns up base-OS packages this service never touches (login,
# mount, ncurses) with no upstream fix yet; failing CI on those forever is
# noise, not a gate. A vulnerability in a package we actually chose — a
# Python dependency, or an OS package with a fix available — still fails.
trivy-image-ingest:
	docker build -f services/ingest/Dockerfile -t ospreyflow/ingest:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/ingest:ci

# services/api's Dockerfile, Phase 3's own — same reasoning as
# trivy-image-ingest above.
trivy-image-api:
	docker build -f services/api/Dockerfile -t ospreyflow/api:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/api:ci

# apps/workspace's Dockerfile — Phase 4's own, paid at Stage 2 §5a as a
# recorded rule 8 repayment rather than an exception (spec/06_DECISIONS.md
# ADR-049). Same reasoning as the two above; the base is Alpine rather than
# Debian, which changes nothing about the gate.
trivy-image-workspace:
	docker build -f apps/workspace/Dockerfile -t ospreyflow/workspace:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/workspace:ci

# harness/Dockerfile — Stage 2 §5b's own bootstrap image (spec/05_DEPLOYMENT.md §2's "one Docker
# command"), paid here as a rule-8 repayment the same way apps/workspace's was at Stage 2 §5a.
trivy-image-harness:
	docker build -f harness/Dockerfile -t ospreyflow/harness:ci .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed ospreyflow/harness:ci

# The one screen for starting and opening the Glass, the Ingest Studio or the Admin console
# (`scripts/launch.py`'s own docstring). It starts an *already-rendered* deployment; the first time,
# `python -m harness.apply` builds one.
launch:
	PYTHONPATH=.:packages $(PY) -m scripts.launch

# Brings a running deployment up to date with this checkout: theme, image builds, up, Keycloak restart
# when its theme changed, sign-in accounts registered again. The launcher's Start runs the same thing.
refresh:
	PYTHONPATH=.:packages $(PY) -m scripts.refresh

# Loads the PaySim dataset into a named case the demo accounts can open, inside the deployment's own
# network (06_DECISIONS.md ADR-055 Amendment 2). Stops the Conduit for the run and starts it again.
seed-paysim:
	PYTHONPATH=.:packages $(PY) -m scripts.seed_internal paysim --stop-api

# The synthetic demos, into named cases the demo accounts can open (ADR-052 Amendment 9).
seed-hmp:
	PYTHONPATH=.:packages $(PY) -m scripts.seed_internal hmp --stop-api

seed-fixture-corp:
	PYTHONPATH=.:packages $(PY) -m scripts.seed_internal fixture-corp --stop-api

seed-ledger:
	PYTHONPATH=.:packages $(PY) -m scripts.seed_internal ledger --stop-api

# Adds the launcher's sign-in (client and demo admin) to a Keycloak that is already running; a
# realm import only happens at first start (06_DECISIONS.md ADR-051). Safe to run again.
register-sign-in:
	PYTHONPATH=.:packages $(PY) -m harness.register_sign_in

dev-up:
	docker compose -f deploy/compose/dev.yaml up -d --wait

dev-down:
	docker compose -f deploy/compose/dev.yaml down -v

# The owner's own ruling, 25 September 2026: removes every OspreyFlow-owned container (any name
# containing "osprey-" — every `docker compose up` this repository's own renderer produces names
# its project `osprey-<profile>`, so this catches a rendered deployment and every exit test's own
# clone of one alike), every OspreyFlow-owned image (`osprey/*:local`, the three owned images'
# local build tags), every named volume containing "osprey", plus dangling images and the build
# cache. **Never the airbyte container or its volumes.** Neither is named or tagged `osprey*`, so
# the name/tag filters above leave them alone unasked; the final `docker volume prune -f` is the
# one step here that is not name-scoped (an exit-test deployment's own *anonymous* volumes — an
# ArcadeDB data volume among them, found here at 2.6GB — carry a random ID, not "osprey", so no
# name filter catches them), and it is still safe for the same reason `docker volume prune`
# always is: it only removes a volume attached to **no** container, so an airbyte volume mounted
# into airbyte's own always-running container is never a candidate regardless of its name.
# Repeatable: run whenever a stale exit-test deployment or dev-up stack has left this host's
# Docker Desktop VM disk short, the condition this session's own exit tests hit twice (`CLAUDE.md`
# rule 14's own worked example, and the disk-exhaustion finding recorded in `07_BUILD_PLAN.md`'s
# Stage 2 §5b entry).
docker-clean:
	@echo "docker-clean: before —"
	@docker system df
	-docker ps -aq --filter "name=osprey-" | xargs -r docker rm -f
	-docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^osprey/.*:local$$' | xargs -r docker rmi -f
	-docker volume ls -q --filter "name=osprey" | xargs -r docker volume rm
	docker image prune -f
	docker builder prune -f
	docker volume prune -f
	@echo "docker-clean: after —"
	@docker system df

# `spec/02_GLASS_FRONTEND.md` §5's performance budget, as a CI gate
# (`apps/workspace/perf/perf.spec.ts`'s own docstring: a software-WebGL
# regression proxy, not the literal hardware numbers). Needs a Chromium
# binary: `npx playwright install chromium --with-deps` once per machine.
glass-perf:
	npm run test:perf --workspace apps/workspace

# `spec/02_GLASS_FRONTEND.md` §6's contrast floor, as a CI gate, both
# themes (`apps/workspace/a11y/a11y.spec.ts`).
glass-a11y:
	npm run test:a11y --workspace apps/workspace

# `process/07_BUILD_PLAN.md` Phase 4's "keyboard navigation reaches every
# canvas action" exit clause, as a CI gate, not an assertion in prose
# (`apps/workspace/keyboard/keyboard.spec.ts`) — a scripted walkthrough
# that never calls `page.mouse`/`.click()`.
glass-keyboard:
	npm run test:keyboard --workspace apps/workspace

# `spec/00_ARCHITECTURE.md` §1.2.1's Verify contrast-floor check — a
# rendered-pixel/reference-image comparison of a fixture graph over the
# basemap's own chrome colours (`apps/workspace/map-verify/contrast.spec.ts`),
# genuinely different from `glass-a11y`'s axe-core DOM-rule check. Dark
# theme only for now — see `map-verify/showcase.tsx`'s own docstring.
glass-map-verify:
	npm run test:map-verify --workspace apps/workspace


# The live tier — the Glass against a stack somebody brought up by hand (`DEMO_GUIDE.md` §3),
# never a showcase page or a mocked API. Never in `check`: it needs real containers, real seeded
# fixtures and a real basemap. Skips itself unless `OSPREY_TEST_LIVE_GLASS=1`.
glass-live:
	npm run test:live --workspace apps/workspace

# `06_DECISIONS.md` ADR-049 Stage 2 §6 amendment 21's own keyboard-driven surface
# (`apps/harness/keyboard/setup-screens.spec.ts`) — the setup screens' own "Save" actions,
# reached by keyboard only, against a real `harness.webapp` server this spec's own
# `playwright.config.ts` starts. Not chained into `ci:` above, the same disclosed
# `make ci`/`ci.yml` divergence `glass-perf`/`glass-a11y`/`glass-keyboard` already have
# (07_BUILD_PLAN.md Stage 6) — it has its own `ci.yml` job instead.
harness-keyboard:
	npm run test:keyboard --workspace apps/harness

# `spec/02_GLASS_FRONTEND.md` §6 / amendment 24, ruling 6 — Stage 2 §6 part C
# (`apps/harness/a11y/a11y.spec.ts`). Against the real `App` from `apps/harness/src` served by a
# real `harness.webapp`, never a showcase page — `glass-a11y`'s own Stage 6 finding named exactly
# that gap for the Glass, and this file's own docstring has the reason it is not reproduced here.
# **In `check`'s own target list, unlike `glass-a11y`/`glass-keyboard`/`harness-keyboard`** — that
# divergence between `make ci` and `ci.yml` is `07_BUILD_PLAN.md` Stage 6's own disclosed gap, not
# repeated for a third surface (Stage 2 §6 part C's own brief). `ci.yml`'s own job runs this as a
# second step of `harness-keyboard-a11y`, not a separate job — it drives the same real `App`
# against the same real `harness.webapp` that job's own `harness-keyboard` step already starts.
harness-a11y:
	npm run test:a11y --workspace apps/harness
