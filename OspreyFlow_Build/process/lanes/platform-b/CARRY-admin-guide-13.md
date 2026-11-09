# Carry for the docs lane: P5b's text (ADR-114 Amendments 37 and 38)

Written by platform-b, 9 November 2026. Neither file below is platform-b's. Apply them to
`OspreyFlow_Core/docs/administration-guide.md` §13 (and its mirror, `spec/10_ADMINISTRATION_GUIDE.md`
§13, if docs keeps the two the same), and to `spec/05_DEPLOYMENT.md` §2.1, as the docs lane's own
change. The behaviour below is on `lane/platform-b`; quote the wording from the code if the two
disagree.

## 1. Administration guide §13: replace the first sentence of the **Lite.** paragraph

> **Every install.** `ospreyflow backup` writes a set to `<backups folder>/<deployment>/<time>-<deployment>-<commit>/`.
> The backups folder is asked for at setup (`folders.backups` in the answers file, the **Backups
> folder** field on the guided page's Folders screen, or the install's prompt), offering
> `~/OspreyFlow/backups`, and is written to `osprey.yaml` as `components.storage.backups`.
> `<deployment>` is the `deployment.name` you gave (`--name`), or the profile (`local-lite`,
> `small`), so two deployments' sets never mix. The set holds the graph store, every PostgreSQL
> database …

(the rest of the paragraph as it stands.)

## 2. §13: replace the **Small on your own server.** paragraph's first sentence

> **Small on your own server.** As every install: written to the backups folder
> (`folders.backups`, or `server.backups`, its older name, section 5a.3; giving both with different
> folders is refused), each set readable by its owner only; …

(the rest as it stands.)

## 3. §13: a new paragraph after **A backup that fails**

> **Where sets are, and cleaning them up.** A backup is never written inside the OspreyFlow
> folder (the checkout: `OspreyFlow_Core`, `OspreyFlow_Build` and the folder holding them).
> `--out-root <folder>` writes a set elsewhere, but a folder inside the checkout is refused, and
> `ospreyflow doctor` fails if the backups folder is inside it. `/var/lib/osprey/backups`, the
> settings' placeholder, is refused at setup except on Small on your own server. A deployment
> installed by name cannot be called `local-lite`, `small` or `cluster`, since the checkout's own
> deployment uses those names for its backups. Give two checkouts on one machine different backups
> folders: both deployments are `local-lite`, so they would otherwise share a subfolder. An `osprey.yaml` from v0.4.x or earlier names no backups folder (or the
> placeholder `/var/lib/osprey/backups`), so its sets go to `~/OspreyFlow/backups/<deployment>/`,
> and the backup's first line says so. Name a folder as `components.storage.backups` to stop that
> line.
>
> Sets taken before this release may still be in the checkout's `backups/`, in a named
> deployment's `~/.ospreyflow/deployments/<name>/backups/`, or directly in a server's backups
> folder. `ospreyflow doctor` names each such folder, with the sets' total size and the one command
> that moves them (`mkdir -p <folder>/<deployment> && mv <sets> <folder>/<deployment>/`). It never
> moves or deletes a set itself. Until they are moved, `ospreyflow restore` with no set lists them
> beside the deployment's own sets, each with its move command, and `ospreyflow restore <set name>`
> still restores one, looking in the deployment's folder first. A set the doctor cannot read all of
> (a server's are the owner's only) is given as "at least" its size, and its move needs `sudo`.
>
> **A synced folder.** A set holds the deployment's data and any real-data exception it was given.
> `ospreyflow doctor` warns when the backups folder is under a folder a sync client copies: on
> macOS, `~/Library/CloudStorage` (Google Drive, OneDrive, Dropbox), `~/Library/Mobile Documents`
> (iCloud Drive), `~/Documents` or `~/Desktop` (which iCloud syncs when "Desktop & Documents" is
> on); and a `OneDrive` folder on any system (Windows, or WSL's `/mnt/c/Users/…`). It is a
> warning, not a refusal, because you may mean it. A folder reached through a link is judged by
> where the link points. `ospreyflow doctor --config <answers>` checks the answers' folder before
> the install.
>
> **Cleaning up.** Nothing removes old sets automatically. Each set is a folder named
> `<UTC time>-<deployment>-<commit>`, the commit in full, for example
> `20261109T020000Z-local-lite-3e5a1c2…` (40 characters). To remove one, delete its folder:
> `rm -rf ~/OspreyFlow/backups/local-lite/<set>`
> (on a server, as the account that runs the backup). Keep at least the newest set that
> `ospreyflow restore` accepts.

## 4. `spec/05_DEPLOYMENT.md` §2.1, the Components screen's row

> | **Components** | Graph store, analytics engine, and the storage roots for data and staging. The backups folder is asked for on the Folders screen of every install (ADR-114 Amendment 37), outside the checkout |

## 5. The guide's settings table (`components.storage.backups`, §… at line ~1348 of `spec/10`)

> | `components.storage.backups` | str | `/var/lib/osprey/backups` | Where backups are written: `<this>/<deployment>/`. Asked at setup (`folders.backups`). The default is a placeholder: an `osprey.yaml` that keeps it (off a server of your own) backs up to `~/OspreyFlow/backups` and says so. |
