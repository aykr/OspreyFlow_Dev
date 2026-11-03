#!/bin/sh
# Publish the marketing site to the product repository's `gh-pages` branch (ADR-114 Amendments 28, 29 and 31).
#
# The product repository is `aykr/OspreyFlow` (Amendment 31 withdrew Amendment 30's move to
# `Solirius/ospreyflow`), and Pages serves the branch at https://aykr.github.io/OspreyFlow/. The site never
# goes through the product export (`make publish-user-repo`) and never reaches `main`: it goes on a branch
# of its own, which GitHub Pages serves.
#
# Only what Pages needs is published: `deploy/index.html`, `deploy/intro-video.html`,
# `deploy/public-sector.html`, `deploy/monitoring.html`, `deploy/assets/`, `deploy/.nojekyll` and, if
# present, `deploy/CNAME`.
#
#   sh OspreyFlow_Build/marketing_site/publish_pages.sh           # commit locally, print the push
#   sh OspreyFlow_Build/marketing_site/publish_pages.sh --push    # and push it
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
DEV="$(cd "$HERE/../.." && pwd)"
PRODUCT="$(cd "$DEV/.." && pwd)/OspreyFlow_user_repo"
DEPLOY="$HERE/deploy"
BRANCH=gh-pages

[ -d "$PRODUCT/.git" ] || { echo "STOP: $PRODUCT is not the product repository's checkout." >&2; exit 1; }
# Only the product repository's own home: never the withdrawn `Solirius/ospreyflow` (Amendment 31).
ORIGIN="$(git -C "$PRODUCT" remote get-url origin 2>/dev/null || true)"
case "$ORIGIN" in
  https://github.com/aykr/OspreyFlow|https://github.com/aykr/OspreyFlow.git|git@github.com:aykr/OspreyFlow.git) ;;
  *) echo "STOP: $PRODUCT's origin is '$ORIGIN', not https://github.com/aykr/OspreyFlow.git." >&2; exit 1 ;;
esac
for f in index.html intro-video.html public-sector.html monitoring.html .nojekyll; do
  [ -f "$DEPLOY/$f" ] || { echo "STOP: $DEPLOY/$f is missing." >&2; exit 1; }
done

# The site may name the company; it must not carry a personal identifier or a path on this machine.
if grep -lI -i -E 'ayan[[:space:]._-]?(d[._-])?kar|ayankarsolirius' "$DEPLOY"/*.html || grep -lI -E '/Users/|/home/' "$DEPLOY"/*.html; then
  echo "STOP: the files above carry a personal identifier or a local path." >&2
  exit 1
fi

git -C "$PRODUCT" fetch -q origin
WORK="$(mktemp -d)/site"
if git -C "$PRODUCT" rev-parse -q --verify "refs/remotes/origin/$BRANCH" >/dev/null; then
  git -C "$PRODUCT" worktree add -q -B "$BRANCH" "$WORK" "origin/$BRANCH"
else
  # First publication: a branch with no history of the product's, holding the site alone.
  git -C "$PRODUCT" worktree add -q --detach "$WORK"
  git -C "$WORK" checkout -q --orphan "$BRANCH"
  git -C "$WORK" rm -rq --cached . >/dev/null 2>&1 || true
  find "$WORK" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
fi
trap 'git -C "$PRODUCT" worktree remove --force "$WORK" >/dev/null 2>&1 || true' EXIT

find "$WORK" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp "$DEPLOY/index.html" "$DEPLOY/intro-video.html" "$DEPLOY/public-sector.html" "$DEPLOY/monitoring.html" "$DEPLOY/.nojekyll" "$WORK/"
cp -R "$DEPLOY/assets" "$WORK/assets"
[ ! -f "$DEPLOY/CNAME" ] || cp "$DEPLOY/CNAME" "$WORK/"

cd "$WORK"
git add -A
if git diff --cached --quiet; then
  echo "Nothing changed since the last publication of the site."
else
  git commit -q -m "Site — from $(git -C "$DEV" rev-parse --short HEAD)"
  git log --oneline -1
fi

if [ "${1:-}" = "--push" ]; then
  git push -q origin "$BRANCH"
  echo "Pushed $BRANCH to $(git -C "$PRODUCT" remote get-url origin)."
else
  echo "Push with:  git -C \"$PRODUCT\" push origin $BRANCH"
fi
