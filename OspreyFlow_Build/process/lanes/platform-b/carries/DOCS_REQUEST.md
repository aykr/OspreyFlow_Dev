# Request to the docs lane (through the orchestrator): the upgrade guide (CARRIES row 106)

Platform-b's carries, 11 November 2026. For the operator-facing upgrade guide, three facts the carries
make true:

1. **Two `start --build` or `update` runs of one deployment at once are refused** ("another refresh or
   update of this deployment is under way"), whichever started first and for the whole of it: an
   `update` holds the deployment from the moment it starts (its "Continue?" question included) to
   its last restart (or rollback). Wait for the
   first to finish. A lock another account left (a run under sudo) that yours cannot open is named,
   with the `sudo rm` that removes it; a folder your account cannot write is named too.
2. **If a command says the compose file needs a value `deployment.env` does not hold** (`stop`,
   `start`, `status`, `logs`, `uninstall`, `map`, `grading`, `models`, `backup`, `restore`, `update`,
   `demo add`, `repair-sign-in`), run the `ospreyflow apply --name <deployment>` it names (it renders
   the file again and keeps or mints every value). A backup set from before that value existed does
   not hold it. If it says the shell sets the value empty, unset it there first (`start --build` says this too). To stop the
   containers meanwhile, use the `docker ps -q --filter label=… | xargs -r docker stop` line it prints.
3. **A restart a dead `update` or `start --build` still owed is done by the next one**, which may
   restart a service once more than strictly needed.

(The row's own wording, "two v0.4.12 updates within one hour are refused", is the rules lane's
rehearsal finding; the guide's wording is the docs lane's.)
