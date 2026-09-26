"""`osprey bundle` — ADR-049's Stage 2 §5b: "Wraps `scripts/osprey_bundle.py`... rather than
writing a second implementation of the same command." `bundle_map_providers` below is the original,
narrower mechanism this module started as (`docs/00_ARCHITECTURE.md` §1.2's own "the bundle step
refuses to package tiles or gazetteers whose profile says `redistributable: false`, and names
them") — kept unchanged and reused, not superseded, by `build_bundle` below, which is the real
`python -m scripts.osprey_bundle --profile <profile> [--images]` command Stage 2 §5b's own brief
describes.

**What `build_bundle` produces**, per that brief's own item 1: the rendered manifests (`compose.
yaml`, `deployment.env`, `versions.lock`, the generated per-deployment `RUNBOOK.md` — all four of
`harness.render.render`'s own artefacts, unchanged), the `osprey.yaml` JSON schema and the example
config this bundle was itself built from, `LICENSE`/`NOTICE`, the documentation site (`scripts.
doc_site`), the hand-maintained `deploy/RUNBOOK.md`, and — with `--images` — an archive of every
image `harness.render.service_images` says the rendered stack runs, each pinned by a
**registry-resolved** digest (`harness.images.registry_digest_resolver`, not the local-daemon one
`harness.render.render` defaults to — a bundle recipient's own daemon has pulled nothing yet, so
only a registry-checkable digest means anything to them). **The three owned services get the same
registry pin as any third-party image, published, round 11:** `.github/workflows/release.yml`
pushes all three to `harness.render.OWNED_IMAGE_REGISTRY` on a tagged release, tagged by exactly
the commit `registry_digest_resolver` is asked to resolve, so a bundle built from a released
commit locks a real digest for them the same way it always has for a third-party image. Built from
an untagged commit, they still resolve to `unresolved`, correctly — no release has published that
exact commit's images, so there is nothing to pin to. Either way `--images` ships them as
`docker save` archives retagged to match the pull-mode reference the bundle's own rendered
`compose.yaml` names, which is what actually lets `docker load` plus this bundle's own
`osprey.yaml.example` deploy correctly.

**Every artefact-hygiene assertion `scripts.packaging_gate` provides runs against the bundle's own
staged file list before it is tarred** — ADR-034 §B7 (no private-tree file, no authorship
identifier) and ADR-035 §C2 (no internal-class demo data) alike. A bundle that fails any of them is
never written to a tarball at all; `RuntimeError` is the refusal, named, per `06_DECISIONS.md`
ADR-035 §C2's own "An assertion on the packaging step, failing the build."

**With `--images`, the workspace image is also layered with the same `docs-site/` the tarball
carries**, at `/usr/share/nginx/html/docs` — item 3's own "into both the tarball and the workspace
image at `/docs`" — via `_docker_build_docs_layer`, whose build context is the rendered `docs-site/`
directory alone, never the repository root, so the new layer can only ever contain what
`doc_site.render_doc_site` already wrote and already checked clean.

No `osprey` CLI yet (`CLAUDE.md`'s own Conventions) — a plain, directly-runnable script, the same
pattern as `scripts/build_local_basemap.py`/`scripts/seed_hmp_fixture.py`. Run as `PYTHONPATH=.:
packages python -m scripts.osprey_bundle --profile local-lite [--images]` from the repo root.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from harness.images import ImageRef, registry_digest_resolver
from harness.render import load_config, render, service_images
from scripts import doc_site, packaging_gate

from schemas.deployment import OspreyConfig
from schemas.mapconfig import MapConfig

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The harness's own bootstrap image (`harness/Dockerfile`, `05_DEPLOYMENT.md` §2's own
#: `ghcr.io/ospreyflow/harness:latest`) — not a compose service, so `harness.render.service_images`
#: never names it, and not archived unless named here explicitly. Item 3 of Stage 2 §5b's own
#: brief: "Include it in the bundle's image set." Same precondition as every other owned image
#: `--images` archives: already built and tagged locally before this command runs; this module
#: does not build it.
HARNESS_IMAGE = "osprey/harness:local"

#: Filesystem debris this machine's own OS/sync tooling writes into any directory it touches
#: — never bundle content, never written by anything above. Found in a real `--images` build, not
#: assumed: `staging_dir.rglob("*")` picked up a stray `Icon\r` (macOS's custom-folder-icon marker,
#: a 0-byte file, name ending in a literal carriage return) inside `dist/`'s own staging tree and
#: `docs-site/`, and it rode straight into the tarball unless filtered here — the same class of
#: junk `git status` already shows scattered across this repository's own working tree, this time
#: reaching a customer-facing artefact instead of only a git status line.
_JUNK_FILENAMES = frozenset({"Icon\r", ".DS_Store"})


def _is_bundle_content(path: Path) -> bool:
    return path.is_file() and path.name not in _JUNK_FILENAMES


@dataclass(frozen=True)
class BundleResult:
    bundled_provider_ids: tuple[str, ...]


class NonRedistributableProviderError(RuntimeError):
    """Names every refused provider — `00_ARCHITECTURE.md` §1.2's "and
    names them", not a bare boolean failure a deployer has to go hunting
    for in the config themselves."""

    def __init__(self, refused_provider_ids: list[str]) -> None:
        self.refused_provider_ids = tuple(refused_provider_ids)
        super().__init__(
            "refusing to bundle non-redistributable provider(s): "
            + ", ".join(refused_provider_ids)
        )


def bundle_map_providers(config: MapConfig) -> BundleResult:
    """Raises `NonRedistributableProviderError` naming every provider whose
    `licence.redistributable` is false; otherwise bundles all of them."""
    refused = [p.id for p in config.providers if not p.licence.redistributable]
    if refused:
        raise NonRedistributableProviderError(refused)
    return BundleResult(bundled_provider_ids=tuple(p.id for p in config.providers))


@dataclass(frozen=True)
class BundleManifest:
    """What `build_bundle` actually wrote, so a caller (the CLI, the exit test) can report or
    assert against it without re-walking the staging directory."""

    profile: str
    files: tuple[str, ...]
    image_archives: tuple[str, ...] = field(default_factory=tuple)


def _docker_tag(local_tag: ImageRef, pull_mode_tag: ImageRef) -> None:
    """Round 07: retags an owned service's already-built local image
    (`osprey/<service>:local`, unchanged precondition) to the pull-mode reference the bundle's
    own render just computed, so the archive `docker load` restores lands under the exact name
    the rendered compose file names — never a real registry pull, never a network call."""
    subprocess.run(["docker", "tag", local_tag, pull_mode_tag], check=True, timeout=60)


def _docker_save(image: ImageRef, out_path: Path) -> None:
    """Archives a real, already-present local image. Does not pull — `build_bundle`'s own caller
    decides whether a missing image is an error or something to fetch first; silently pulling
    inside a save step would hide a multi-gigabyte network operation behind what looks like a
    filesystem write."""
    subprocess.run(
        ["docker", "save", "-o", str(out_path), image], check=True, timeout=1200
    )


def _docker_build_docs_layer(base_image: ImageRef, docs_site_dir: Path, tag: ImageRef) -> None:
    """Layers the bundle's own already-rendered, already-gate-checked `docs-site/` onto a real,
    already-present local image — the other half of item 3's "into both the tarball and the
    workspace image at `/docs`". The build context is `docs_site_dir` alone, never the repository
    root: this is what guarantees the new layer can only ever contain what
    `doc_site.render_doc_site` already wrote and already ran `assert_no_private_tree_names`
    against, not a second, independent chance for a private-tree file to reach an image layer.

    Retags as `tag` — `build_bundle`'s own caller passes the image's own existing reference, so the
    augmented image replaces it under the same name `compose.yaml`/`versions.lock` already cite, and
    a bundle recipient's `docker load` restores exactly the reference the rendered manifests expect,
    not a second, differently-named image nothing else in the bundle points at.
    """
    dockerfile_path = docs_site_dir.parent / "Dockerfile.docs-layer"
    dockerfile_path.write_text(
        f"FROM {base_image}\nCOPY . /usr/share/nginx/html/docs/\n", encoding="utf-8"
    )
    try:
        subprocess.run(
            ["docker", "build", "-f", str(dockerfile_path), "-t", tag, str(docs_site_dir)],
            check=True,
            timeout=300,
        )
    finally:
        dockerfile_path.unlink()


def _text_blobs(staging_dir: Path) -> dict[str, str]:
    """Every non-binary staged file's own content, keyed by its path relative to the staging
    root — what `packaging_gate.find_authorship_identifiers` scans. Binary files (image archives)
    are skipped; `find_private_tree_files`/`find_internal_demo_data` already cover them by path
    alone, and decoding a multi-gigabyte tar as UTF-8 to search it is not what this check is for.
    """
    blobs: dict[str, str] = {}
    for path in staging_dir.rglob("*"):
        if not _is_bundle_content(path) or path.suffix in (".tar", ".gz", ".tgz"):
            continue
        try:
            blobs[str(path.relative_to(staging_dir))] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return blobs


def build_bundle(
    config: OspreyConfig,
    staging_dir: Path,
    *,
    example_config_text: str,
    include_images: bool = False,
    docker_save: Callable[[ImageRef, Path], None] = _docker_save,
    docker_build_docs_layer: Callable[[ImageRef, Path, ImageRef], None] = _docker_build_docs_layer,
    docker_tag: Callable[[ImageRef, ImageRef], None] = _docker_tag,
    resolver: Callable[[ImageRef], str | None] = registry_digest_resolver,
) -> BundleManifest:
    """Stages a whole bundle's own contents under `staging_dir` (not yet tarred — `make_tarball`
    below does that) and refuses, via `packaging_gate.check_artefact`, to leave anything staged
    that fails ADR-034 §B7 or ADR-035 §C2. `RuntimeError` on refusal names every finding; nothing
    is silently dropped from a bundle that fails.

    `resolver` defaults to the real, registry-backed one; tests inject a fake so the fast unit
    tier never makes a real network call."""
    staging_dir.mkdir(parents=True, exist_ok=True)

    map_config = config.map
    if map_config is not None:
        bundle_map_providers(map_config)  # 00_ARCHITECTURE.md §1.2 — refuses by name, unchanged.

    # Round 07: `config` (not a build-declaring copy of it) is what a recipient's own `harness.
    # apply --config osprey.yaml.example` re-renders from — so this bundle's own `compose.yaml`/
    # `versions.lock` must be the **pull-mode** render, the shape the recipient's own re-render
    # produces, not the build-mode one this checkout could produce for itself. `--images` below
    # builds the owned services from source exactly as before, then retags each one under the
    # pull-mode reference `service_images` just computed, before saving — the archive `docker
    # load` restores lands under the identical name the rendered compose file references, closing
    # exactly the mismatch a real run of this test found: pull-mode `compose.yaml` naming
    # `ghcr.io/ospreyflow/api:<sha>` while the archive still carried `osprey/api:local`.
    rendered = render(
        config,
        resolver=resolver,
        allow_unpinned=True,
        resolved_source_label="registry",
    )
    for name, content in rendered.artefacts.items():
        (staging_dir / name).write_text(content, encoding="utf-8")

    (staging_dir / "LICENSE").write_text(
        (REPO_ROOT / "LICENSE").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (staging_dir / "NOTICE").write_text(
        (REPO_ROOT / "NOTICE").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (staging_dir / "osprey.schema.json").write_text(
        json.dumps(OspreyConfig.model_json_schema(), indent=2, sort_keys=True), encoding="utf-8"
    )
    (staging_dir / "osprey.yaml.example").write_text(example_config_text, encoding="utf-8")

    deploy_runbook_path = REPO_ROOT / "deploy" / "RUNBOOK.md"
    deploy_runbook_text = (
        deploy_runbook_path.read_text(encoding="utf-8") if deploy_runbook_path.is_file() else None
    )
    if deploy_runbook_text is not None:
        (staging_dir / "deploy-RUNBOOK.md").write_text(deploy_runbook_text, encoding="utf-8")

    doc_site.render_doc_site(
        staging_dir / "docs-site",
        generated_runbook_text=rendered.artefacts.get("RUNBOOK.md"),
        deploy_runbook_text=deploy_runbook_text,
    )

    image_archives: list[str] = []
    if include_images:
        images_dir = staging_dir / "images"
        images_dir.mkdir()
        for entry in service_images(config):
            if entry.owned:
                # Built from this checkout under the developer/CI tag (`osprey_bundle.py`'s own
                # precondition: "already built and tagged locally before this command runs" —
                # unchanged this round), then retagged to the pull-mode reference `entry.image`
                # actually is here, so the archive `docker load` restores matches what the
                # bundle's own rendered compose file names, not a tag nothing local answers to.
                docker_tag(f"osprey/{entry.service}:local", entry.image)
            if entry.service == "workspace":
                docker_build_docs_layer(entry.image, staging_dir / "docs-site", entry.image)
            archive_relpath = f"images/{entry.service}.tar"
            docker_save(entry.image, staging_dir / archive_relpath)
            image_archives.append(archive_relpath)
        harness_archive_relpath = "images/harness.tar"
        docker_save(HARNESS_IMAGE, staging_dir / harness_archive_relpath)
        image_archives.append(harness_archive_relpath)

    all_paths = sorted(
        str(p.relative_to(staging_dir)) for p in staging_dir.rglob("*") if _is_bundle_content(p)
    )
    findings = packaging_gate.check_artefact(
        all_paths, text_blobs=_text_blobs(staging_dir)
    )
    if findings:
        raise RuntimeError(f"osprey bundle: refusing to package this artefact: {findings}")

    return BundleManifest(
        profile=config.profile.value, files=tuple(all_paths), image_archives=tuple(image_archives)
    )


def make_tarball(staging_dir: Path, out_path: Path) -> Path:
    """One artefact — "an artefact a customer receives" (this module's own docstring) — not a
    manifest bundle plus loose image files sitting beside it. Uncompressed when it carries image
    archives (already-compressed layer data gains nothing from a second gzip pass and it costs real
    time on a multi-gigabyte tar); compressed otherwise, since the manifests/docs are plain text."""
    mode = "w" if any(staging_dir.glob("images/*.tar")) else "w:gz"
    with tarfile.open(out_path, mode) as tar:
        for path in sorted(staging_dir.rglob("*")):
            if _is_bundle_content(path):
                tar.add(path, arcname=str(path.relative_to(staging_dir)))
    return out_path


# --- CLI entrypoint, mirroring scripts/seed_hmp_fixture.py's shape -----------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.osprey_bundle",
        description="Builds a distributable OspreyFlow deployment bundle for one profile.",
    )
    parser.add_argument("--profile", default=None, help="Overrides osprey.yaml's own profile.")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "osprey.yaml")
    parser.add_argument(
        "--out", type=Path, default=REPO_ROOT / "dist", help="Directory to write the bundle into."
    )
    parser.add_argument(
        "--images",
        action="store_true",
        help="Also archive every image the rendered stack runs, pinned by registry digest.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from schemas.deployment import Profile

    args = _parse_args(argv if argv is not None else sys.argv[1:])
    config = load_config(args.config)
    if args.profile:
        config = config.model_copy(update={"profile": Profile(args.profile)})

    args.out.mkdir(parents=True, exist_ok=True)
    staging_dir = args.out / f"osprey-bundle-{config.profile.value}-staging"
    manifest = build_bundle(
        config,
        staging_dir,
        example_config_text=args.config.read_text(encoding="utf-8"),
        include_images=args.images,
    )
    extension = "tar" if manifest.image_archives else "tar.gz"
    tarball_path = args.out / f"osprey-bundle-{config.profile.value}.{extension}"
    make_tarball(staging_dir, tarball_path)

    print(
        f"osprey bundle: {len(manifest.files)} file(s)"
        + (f", {len(manifest.image_archives)} image archive(s)" if manifest.image_archives else "")
        + f" -> {tarball_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
