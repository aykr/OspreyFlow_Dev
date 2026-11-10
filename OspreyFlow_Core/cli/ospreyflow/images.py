"""`ospreyflow images push --registry <registry>` (`spec/06_DECISIONS.md` ADR-148 decision 8):
every image a `cloud-platform` render names, into the namespace's registry (ECR, scanned on push).
Ours are built from this checkout and pushed (the Conduit without Java, decision 12); the
third-party ones are copied by their digest, so the copy is the image the values pin.

It follows the render's `images.yaml` (`deploy/generated/cloud-platform/`): render first, push,
then render again, which pins ours by the digest the registry gives for its copy. Signing in to the
registry is the person's own (`aws ecr get-login-password | docker login …`), never this command's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .home import CommandRefused
from .run import Runner

PLAN = Path("deploy") / "generated" / "cloud-platform" / "images.yaml"


def read_plan(product: Path, folder: Path | None = None) -> dict[str, Any]:
    path = (folder / "images.yaml") if folder is not None else product / PLAN
    if not path.is_file():
        raise CommandRefused(
            f"No image plan at {path}: render the cloud-platform profile first "
            "(python -m harness.render)."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def steps(plan: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Each step in order, in words and as its command: ours built and pushed, theirs copied."""
    out: list[tuple[str, list[str]]] = []
    for image in plan["images"]:
        target = image["target"]
        if "dockerfile" in image:
            build = ["docker", "build", "-f", image["dockerfile"]]
            for name, value in sorted(image.get("build_args", {}).items()):
                build += ["--build-arg", f"{name}={value}"]
            out.append((f"build {target}", [*build, "-t", target, image["context"]]))
            out.append((f"push {target}", ["docker", "push", target]))
        else:
            out.append(
                (f"copy {image['source']} to {target}",
                 ["docker", "buildx", "imagetools", "create", "--tag", target, image["source"]])
            )  # fmt: skip
    return out


def push(
    product: Path,
    run: Runner,
    *,
    registry: str,
    folder: Path | None = None,
    dry_run: bool = False,
    say: Any = print,
) -> int:
    plan = read_plan(product, folder)
    if registry.rstrip("/") != plan["registry"]:
        raise CommandRefused(
            f"The render names the registry {plan['registry']}, not {registry}: the values would "
            "pull from somewhere else. Set cloud_platform.registry and render again."
        )
    todo = steps(plan)
    for words, argv in todo:
        say(("would " if dry_run else "") + words)
        if dry_run:
            continue
        code = run(argv, cwd=product)
        if code != 0:
            say(
                f"The step '{words}' failed (exit {code}); nothing after it was run. If the "
                "registry refused it, sign in to it first."
            )
            return code
    if not dry_run:
        say(
            f"{len(plan['images'])} images are in {registry}. Render again to pin ours by the "
            "digest the registry gives for its copy."
        )
    return 0


def add_parser(verbs: Any) -> None:
    images = verbs.add_parser(
        "images", help="copy a cloud-platform render's images to its registry"
    )
    actions = images.add_subparsers(dest="action", metavar="ACTION", required=True)
    push_verb = actions.add_parser(
        "push", help="build ours and copy the third-party ones, by digest, into the registry"
    )
    push_verb.add_argument("--registry", required=True, help="the namespace's registry (ECR)")
    push_verb.add_argument(
        "--from",
        dest="folder",
        type=Path,
        help="the render's folder (default: deploy/generated/cloud-platform)",
    )
    push_verb.add_argument("--dry-run", action="store_true", help="say each step; run none")


def main_action(args: Any, product: Path, run: Runner) -> int:
    return push(product, run, registry=args.registry, folder=args.folder, dry_run=args.dry_run)
