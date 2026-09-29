# apps/workspace — the Glass, built by Vite and served as static files.
#
# Standing rule (process/07_BUILD_PLAN.md, "Standing rules for the whole
# build"): each service gets its own image, and a `trivy image` CI scan,
# in the phase that creates it — not batched into Phase 8. This one was
# batched into Phase 8, and that is a recorded rule 8 repayment rather
# than an exception: the Glass has had no image since Phase 4 created it,
# and Stage 2 §5a pays that debt once. The rule keeps its full force.
#
# Unlike the two Python service images, this produces no long-running
# application process of its own: `vite build` emits a directory of static
# assets and the runtime stage only has to serve them. That is why the
# final stage is nginx rather than Node — there is no server-side
# rendering, no API layer here, and shipping a Node runtime to serve
# static files would add an interpreter and its whole dependency surface
# to the image for nothing.

FROM node:22-slim AS builder

WORKDIR /app

# The npm workspace root, then the workspace itself. `npm ci` needs the
# root lockfile and both manifests before any source, so this layer caches
# across source-only changes.
COPY package.json package-lock.json ./
COPY apps/workspace/package.json ./apps/workspace/
RUN npm ci

# `tokens.css` moved into the product tree at Trigger A (round 14a, ADR-034 §B8) —
# `apps/workspace/src/design/tokens.css`, inside the `COPY apps/workspace` line below. No
# separate COPY or `.dockerignore` negation is needed any more; both existed only because the
# file used to live under the private `docs/` tree this image otherwise excludes wholesale.
COPY tsconfig.json ./
COPY apps/workspace ./apps/workspace

# **Same-origin, so the bundle carries no address** (05_DEPLOYMENT.md
# §2.6 item 1, the owner's decision of 25 September 2026). Vite inlines
# `import.meta.env.VITE_*` at build time, so whatever is set here is what
# every deployment built from this image sends requests to, forever. An
# empty string is the whole point: `App.tsx` then issues relative paths
# and this image's own nginx (see nginx.conf) proxies /v1 to the Conduit.
#
# Set as an `ENV`, not an `ARG`: an `ARG` can be overridden at build time
# with `--build-arg`, and the one thing this must not be is overridable
# into an absolute URL. `tests/harness/test_workspace_bundle.py` asserts
# the built bundle contains no absolute API URL and is shown red against a
# planted one.
ENV VITE_API_BASE_URL=""

RUN npm run build --workspace apps/workspace

FROM nginx:1.27-alpine

# Base-image OS packages lag the upstream image's own last-published point
# release; picking up current Alpine security patches at build time is
# what keeps `trivy image` a real gate rather than permanently red on
# packages this image does not use.
RUN apk upgrade --no-cache

# A single-page application: every unknown path is the app's own route,
# not a 404, or a deep link into an investigation breaks on refresh.
# spec/05_DEPLOYMENT.md §7 requires a non-root, read-only-root posture, so
# nginx runs unprivileged on 8080 rather than root on 80.
COPY apps/workspace/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/apps/workspace/dist /usr/share/nginx/html

RUN touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD ["/bin/sh", "-c", "wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1"]

CMD ["nginx", "-g", "daemon off;"]
