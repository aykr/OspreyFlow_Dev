# Request to the docs lane (through the orchestrator): the upgrade guide (CARRIES row 106)

Platform-b's carries, 11 November 2026. For the operator-facing upgrade guide, three facts the carries
make true:

1. **Two `start --build` or `update` runs of one deployment at once are refused** ("another refresh of
   this deployment is under way"): wait for the first to finish.
2. **If `stop`, `start`, `status` or `logs` says the compose file needs a value `deployment.env` does
   not hold**, run `ospreyflow apply` (it renders the file again and keeps or mints every value). A
   backup set from before that value existed does not hold it. To stop the containers meanwhile, use
   the `docker stop $(docker ps -q --filter label=…)` line the command prints.
3. **A restart a dead `update` or `start --build` still owed is done by the next one**, which may
   restart a service once more than strictly needed.

(The row's own wording, "two v0.4.12 updates within one hour are refused", is the rules lane's
rehearsal finding; the guide's wording is the docs lane's.)
