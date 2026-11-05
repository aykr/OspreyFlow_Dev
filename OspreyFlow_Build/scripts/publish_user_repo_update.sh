#!/bin/sh
# Publish the current HEAD to the user repository as a new commit (ADR-114 Amendment 21).
# Run by the owner; not committed. The first publication was publish_user_repo_first.sh.
set -eu
ROOT=/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform
USER_REPO="$ROOT/OspreyFlow_user_repo"
FRESH="$(mktemp -d)/export"

[ -d "$USER_REPO/.git" ] || { echo "STOP: $USER_REPO is not the user repository's checkout." >&2; exit 1; }
[ -z "$(git -C "$USER_REPO" status --porcelain)" ] || { echo "STOP: $USER_REPO has uncommitted changes." >&2; exit 1; }

make -C "$ROOT/ospreyflow/OspreyFlow_Build" publish-user-repo COMMIT=HEAD OUT="$FRESH"

# Names any case; the local path case-sensitively (Keycloak's API paths are /users/).
if grep -rlI -i -E 'skilling|fastow|dasovich|ayankar' "$FRESH" || grep -rlI -E '/Users/' "$FRESH"; then
  echo "STOP: the files above name a real person or a local path." >&2
  exit 1
fi
for p in osprey.local.yaml data deployment.env config/real_data_exceptions.yaml; do
  [ ! -e "$FRESH/$p" ] || { echo "STOP: $p must not be published." >&2; exit 1; }
done

# Mirror the export over the checkout, its history kept; a file gone from the product goes here too.
rsync -a --delete --exclude .git "$FRESH/" "$USER_REPO/"

cd "$USER_REPO"
git add -A
if git diff --cached --quiet; then
  echo "Nothing changed since the last publication."
  exit 0
fi
git diff --cached --stat | tail -3
git commit -q -m "OspreyFlow — from $(git -C "$ROOT/ospreyflow" rev-parse --short HEAD)"
git log --oneline -1
echo "Push with:  git -C \"$USER_REPO\" push origin main"
