# Demo lane handoff · osprey-small (13 November 2026, closed after the onepass deploy)

**State.** `ssh ospreyflow-test`, `/opt/ospreyflow`, Compose project osprey-small, https://govuk.ospreyflow.app (and `id.`, `bi.`); 443 is open to the owner's IP only. Code: main 33084d7. `osprey.yaml`: `network.access_key: true` (one prompt, Am 42); `appearance.brand: govuk`; `banner_text` "Demonstration only: …"; `resources.memory_gib: 62`; resolution off. At handover: 16 running, 12 healthy, four sign-ins pass, the gate holds. The server's `.git` is still at v0.5.0, so **always `--build`; never a bare install**.

**Ways back** (all on the server; everything runs as `osprey` unless it says root):
- Remove the gate: `cp -p osprey.yaml.before-access-key osprey.yaml`, then one `apply`.
- Remove the banner: `osprey.yaml.before-banner`, then `apply`. Old address: `osprey.yaml.before-govuk-app-20261112T181854Z`, then `apply` and `repair-sign-in`. Older: `.before-sendable`, `.before-resolution-off`.
- Undo onepass (as root): copy `/root/rebuild-2026-11-12/{Caddyfile,access-key.caddy}.before-onepass` into `deploy/generated/small/`, keeping the key file 600 and osprey's, then restart the proxy. Or copy 4196468's harness back and run `apply`.
- Data: `/srv/ospreyflow/backups/small/20261113T065402Z-small-2be985a…` (06:54, taken with the Conduit running).

**Deploy recipe** (from a worktree on the Mac):
1. `git archive <sha> OspreyFlow_Core | tar -x -C <scratch>/core`
2. Dry run first. Write the excludes out, because zsh does not split a variable, and an unsplit one listed `.venv` for deletion: `rsync -a --delete --dry-run --itemize-changes --rsync-path="sudo -u osprey rsync" --exclude=/.git --exclude=/.venv --exclude='/install.yaml*' --exclude='/osprey.yaml*' --exclude=/deploy/generated/ --exclude=/data/ --exclude=/.install --exclude=node_modules <scratch>/core/OspreyFlow_Core/ ospreyflow-test:/opt/ospreyflow/`. Only `__pycache__` deletions are expected; anything else goes to the orchestrator. A root-owned `__pycache__` blocks the delete: remove it as root.
3. The same command without `--dry-run`, then on the server: `cd /opt/ospreyflow && sudo -u osprey -H bash -c "PATH=/home/osprey/.local/bin:\$PATH PYTHONPATH=cli:.:packages .venv/bin/python -m ospreyflow.main <verb> < /dev/null"`. Run `uv sync --frozen --extra extraction` only when the lock changed.
4. `apply` re-renders from `osprey.yaml` (Caddyfile, glass.json, theme, key file) and restarts what changed; it **never builds**. `start --build` rebuilds owned images (`apps/workspace`, `services`); it **never re-renders** the Caddyfile or key file. A Glass/Conduit change needs `start --build`; a harness or `osprey.yaml` change needs `apply`; both kinds need both.
5. Logs go to `/root/rebuild-2026-11-12/NN-*.log` (chmod 600). Take a `backup` first for anything that changes data.

**Checks** (root): `cd /root/rebuild-2026-11-12 && /opt/ospreyflow/.venv/bin/python demo_checks.py gate|signin`. `gate`: each name without the pass, expecting 401, a key prompt and noindex. `signin`: the four demo accounts through the Keycloak form, PASS/FAIL. Passwords come from `deployment.env`; the gate is passed with `harness.access_key.pass_token` (the host-tool pass). It prints neither, nor the key.
- `switch-to-{ospreyflow,govuk}.sh` are the owner's to run and have never been run.
- Browser checks: Playwright headless shell on the Mac, scripts in the session scratchpad. Pipe the password and the pass in over ssh stdin; print neither.

**Queued (orchestrator's word):** the slim header; the rail with Help; refresh. After the demo: the memory cap (`resources.memory_gib` 62 → 24, one `apply`, check, record ArcadeDB's heap and free memory; "unload when idle" needs code: `OLLAMA_KEEP_ALIVE` is fixed at -1 in `harness/render.py`); R1.

**Open:** certificate renewal is manual before 10 Feb 2027 (DNS-01); remove the four demo accounts before anything goes public; the GOV.UK header still shows the crown; Superset's login has no banner; `install.yaml` names the old address.

**Last commit before this pause:** 1aaa354. Nothing was running at the pause; the next session must not redo any deploy listed above.
