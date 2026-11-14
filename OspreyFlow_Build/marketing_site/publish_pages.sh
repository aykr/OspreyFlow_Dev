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
#
# ospreyflow.org and ospreyflow.net are each their own repository, which the owner creates, each with its own
# Pages site on its own `gh-pages` branch and its own domain (`sites/<site>/CNAME`). Each is published whole
# from `sites/<site>/`, after the same checks, into a checkout beside this one (`OspreyFlow_site_<site>`) whose
# origin must be the address `sites/REPOSITORIES` gives; until the owner has written it there, it stops:
#
#   sh OspreyFlow_Build/marketing_site/publish_pages.sh --site org          # commit locally, print the push
#   sh OspreyFlow_Build/marketing_site/publish_pages.sh --site net --push   # and push it
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
DEV="$(cd "$HERE/../.." && pwd)"
BRANCH=gh-pages
SITE=""
PUSH=""
# The arguments in any order; anything else stops before anything is done.
while [ $# -gt 0 ]; do
  case "$1" in
    --push) PUSH=1; shift ;;
    --site)
      # An empty site (`--site ""`) stops too: it must never fall through to the current site.
      [ $# -ge 2 ] && [ -n "$2" ] || { echo "STOP: --site takes org or net." >&2; exit 1; }
      SITE="$2"; shift 2 ;;
    *) echo "STOP: unknown argument '$1' (--site org|net, --push)." >&2; exit 1 ;;
  esac
done
case "$SITE" in
  "")
    PRODUCT="$(cd "$DEV/.." && pwd)/OspreyFlow_user_repo"
    DEPLOY="$HERE/deploy"
    EXPECTED="https://github.com/aykr/OspreyFlow" ;;
  org|net)
    PRODUCT="$(cd "$DEV/.." && pwd)/OspreyFlow_site_$SITE"
    DEPLOY="$HERE/sites/$SITE"
    # One line a site, `<site> https://github.com/<owner>/<repository>`, written by the owner once it exists.
    EXPECTED="$(awk -v s="$SITE" '$1 == s { print $2 }' "$HERE/sites/REPOSITORIES")"
    case "$EXPECTED" in
      https://github.com/*/*) ;;
      *) echo "STOP: sites/REPOSITORIES gives no repository for $SITE yet; the owner creates it and writes it there." >&2; exit 1 ;;
    esac ;;
  *) echo "STOP: --site takes org or net." >&2; exit 1 ;;
esac

[ -d "$PRODUCT/.git" ] || { echo "STOP: $PRODUCT is not the product repository's checkout." >&2; exit 1; }
# Only the site's own repository: for the current site, never the withdrawn `Solirius/ospreyflow` (Amendment 31).
ORIGIN="$(git -C "$PRODUCT" remote get-url origin 2>/dev/null || true)"
SSH="git@github.com:${EXPECTED#https://github.com/}.git"
case "$ORIGIN" in
  "$EXPECTED"|"$EXPECTED.git"|"$SSH") ;;
  *) echo "STOP: $PRODUCT's origin is '$ORIGIN', not $EXPECTED.git." >&2; exit 1 ;;
esac
if [ -z "$SITE" ]; then
  FILES="index.html intro-video.html public-sector.html monitoring.html .nojekyll"
else
  FILES="index.html"
fi
for f in $FILES; do
  [ -f "$DEPLOY/$f" ] || { echo "STOP: $DEPLOY/$f is missing." >&2; exit 1; }
done

# The site may name the company; it must not carry a personal identifier or a path on this machine. The one
# exception is ospreyflow.org's Team page, which names the six people in TEAM_NAMES, in their own cards and
# nowhere else (the owner's decision, 12 November 2026; identifier_check.py, tests/test_site_identifiers.py).
if ! python3 "$HERE/identifier_check.py" "$DEPLOY"; then
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
if [ -z "$SITE" ]; then
  cp "$DEPLOY/index.html" "$DEPLOY/intro-video.html" "$DEPLOY/public-sector.html" "$DEPLOY/monitoring.html" "$DEPLOY/.nojekyll" "$WORK/"
  cp -R "$DEPLOY/assets" "$WORK/assets"
  [ ! -f "$DEPLOY/CNAME" ] || cp "$DEPLOY/CNAME" "$WORK/"
else
  # A generated site is published whole: every file build.py wrote, nothing else (no README, no build.py), and the two
  # files Pages reads, written here so build.py's output and its drift test are unchanged.
  cp -R "$DEPLOY/." "$WORK/"
  : > "$WORK/.nojekyll"
  echo "ospreyflow.$SITE" > "$WORK/CNAME"
fi

cd "$WORK"
git add -A
if git diff --cached --quiet; then
  echo "Nothing changed since the last publication of the site."
else
  git commit -q -m "Site${SITE:+ $SITE} — from $(git -C "$DEV" rev-parse --short HEAD)"
  git log --oneline -1
fi

if [ -n "$PUSH" ]; then
  git push -q origin "$BRANCH"
  echo "Pushed $BRANCH to $(git -C "$PRODUCT" remote get-url origin)."
else
  echo "Push with:  git -C \"$PRODUCT\" push origin $BRANCH"
fi
