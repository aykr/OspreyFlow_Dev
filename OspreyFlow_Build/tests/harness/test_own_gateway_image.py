"""PL13b: OspreyFlow's own model-gateway image, built from the publisher's MIT files alone.

The owner's ruling of 21 November 2026: the gateway is built by us from the MIT code, without the
publisher's commercially licensed folder (`/app/enterprise`) or its proprietary package
(`litellm-enterprise`), scanned, signed and released like the other images. The scout
(`spec/PL13_GATEWAY_SCOUT.md`, rows 3, 5, 6 and 9) found the cut clean; this file holds the build to
it. Nothing here builds an image or starts a container (the build and its live runs are the
builder's report and an owed live test); every case reads files or renders in memory.

**Which folders it walks.** `git ls-files` of `OspreyFlow_Core` (the whole tracked product tree,
read once, for the one case that no product file names the publisher's image); and by fixed path:
the gateway's own folder `OspreyFlow_Core/deploy/litellm/`, `deploy/compose/dev.yaml`,
`harness/cloud_platform/profile.yaml` and `poc_manifest.yaml`, `docs/administration-guide.md`, and
`OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md` and `spec/LICENCE_REGISTER.yaml`. The register
gate's own walk (`tools.licence_register.read_sources`) runs over the product as it is.

**What would fail, and the planted fault that shows it** (CLAUDE.md rules 12 and 15; each fault has
the shape the code under test really sees, the publisher's own Dockerfile line, a `pip freeze` line
of the pinned image's venv, an installed distribution's own `METADATA`, or the renderer's own
stanza, not a hand-written approximation):

- the image contains the commercial folder or package: `dockerfile_problems`, `constraints_problems`
  and `overrides_problems` over the real files, and the publisher's `COPY --from=builder
  /app/enterprise /app/enterprise`, a freeze line, the venv's `file:///app/enterprise` direct URL
  and a `FROM` of the publisher's image planted in them;
- a proprietary distribution gets into the build: the gate over a site-packages folder holding a
  distribution's real `METADATA` (`License-Expression: LicenseRef-Proprietary`), under the package's
  own name and under another's, and a bare copy of the package's folder with no metadata;
- the gateway is handed the deployment's whole environment: the rendered stanza with
  `env_file: [deployment.env]` (what `ServiceImage.owned` gave every owned service) planted back;
- the product still names the publisher's image: a planted file in a scratch tree and the real walk;
- the gateway's places part: every place that holds its Dockerfile or its pin is compared.

Not provable here, and owed (each a live test, or the owner's step): the image building and
starting, the route script and `test_model_gateway_live.py` against it, the release workflow
building, scanning and signing it, and `harness/signatures.py`'s check of an older lock (the
protected patch carries its own tests).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import re
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from harness.release_lock import release_images, render_release_lock
from harness.render import git_sha, render, service_images
from tools import licence_register
from tools.cp_policy_check import final_user
from tools.layout import BUILD, CORE
from tools.licence_check import _instructions

from schemas.deployment import ModelProviderConfig, ModelsConfig, OspreyConfig

FOLDER = CORE / "deploy" / "litellm"
DOCKERFILE_PATH = "deploy/litellm/Dockerfile"
#: The base the publisher's own Dockerfile names for both its stages (scout row 5), and the uv image
#: it installs with (revision 18243cd7).
WOLFI = "cgr.dev/chainguard/wolfi-base"
UV = "ghcr.io/astral-sh/uv"
PUBLISHERS_IMAGE = (
    "ghcr.io/berriai/litellm@sha256:"
    "d295634e09c648dcdb72c4cc2dd226f5fb87823a73e88cbbed6f205e4deb044b"
)
#: What the final stage may copy from the builder: the venv, the two entrypoint scripts' folder, the
#: schema, the migration script and the Prisma CLI and engines (the brief, item 1).
FINAL_COPIES_FROM_BUILDER = frozenset(
    {
        "/app/.venv",
        "/app/docker",
        "/app/schema.prisma",
        "/app/litellm/proxy/prisma_migration.py",
        "/opt/prisma",
    }
)
#: What the final stage may copy from the build context: the two scripts' folder and the gate.
FINAL_COPIES_FROM_CONTEXT = frozenset({"docker", "licence_gate.py"})
EXTRAS = {"proxy", "proxy-runtime", "extra_proxy", "semantic-router", "saml", "bedrock-realtime"}
OVERRIDE_LINE = 'litellm-enterprise ; python_version < "0"'
#: The two entrypoint scripts, byte for byte as the publisher's repository holds them at revision
#: 18243cd7 (the pinned image's own copies, compared with GitHub's: identical).
ENTRYPOINT_SHA256 = {
    "prod_entrypoint.sh": "6265520d64e737623031e0d421dbd58675c5e20bba06cfe4172706b9d5fd9558",
    "entrypoint.sh": "28d6fd672a96d22be895c0d7f457aeb4beb28c11d3c0d3e799cbbef4c47869c7",
}
#: The stanza the renderer gave the gateway before this slice, less its image: every line of it
#: stays (the ruling: unchanged byte for byte except the image reference).
GATEWAY_STANZA = {
    "command": ["--config", "/app/config.yaml", "--port", "4000"],
    "depends_on": {
        "litellm-db": {"condition": "service_completed_successfully"},
        "ollama": {"condition": "service_started"},
    },
    "environment": {
        "DATABASE_URL": "postgresql://litellm:${OSPREY_LITELLM_DB_PASSWORD:?set in the deployment "
        "env file}@postgres:5432/litellm",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "LITELLM_MASTER_KEY": "${OSPREY_LITELLM_MASTER_SECRET:?set in the deployment env file}",
        "LITELLM_SALT_KEY": "${OSPREY_LITELLM_SALT_SECRET:?set in the deployment env file}",
        "STORE_MODEL_IN_DB": "True",
    },
    "healthcheck": {
        "interval": "5s",
        "retries": 20,
        "start_period": "30s",
        "test": [
            "CMD",
            "python3",
            "-c",
            "import urllib.request; urllib.request.urlopen('http://localhost:4000/health/liveliness')",
        ],
        "timeout": "5s",
    },
    "networks": ["osprey"],
    "restart": "unless-stopped",
    "volumes": ["./litellm.yaml:/app/config.yaml:ro"],
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- the Dockerfile, the constraints file and the override ---------------------------------------


def _stages(text: str) -> list[list[str]]:
    """The instructions of each stage, in order (continued lines joined, comments left out)."""
    stages: list[list[str]] = []
    for instruction in _instructions(text):
        if instruction.split(None, 1)[0].upper() == "FROM":
            stages.append([])
        if stages:
            stages[-1].append(instruction)
    return stages


def _copy_sources(instruction: str) -> tuple[str | None, list[str]]:
    """`(the stage copied from, the sources)` of a `COPY`, its destination left out."""
    words = instruction.split()[1:]
    origin = None
    paths = []
    for word in words:
        if word.startswith("--from="):
            origin = word.removeprefix("--from=")
        elif not word.startswith("--"):
            paths.append(word)
    return origin, paths[:-1]


def dockerfile_problems(text: str) -> list[str]:
    """Why a Dockerfile could put the commercially licensed folder or package, or the publisher's
    image, into the gateway; empty when it cannot."""
    problems: list[str] = []
    if re.search(r"enterprise", text, re.I):
        problems.append("names the commercially licensed folder, package or archives")
    stages = _stages(text)
    if len(stages) < 2:
        return [*problems, "is not a builder stage and a runtime stage"]
    aliases = {
        m.group(1).lower()
        for s in stages
        if (m := re.match(r"FROM\s+(?:--\S+\s+)*\S+\s+AS\s+(\S+)", s[0], re.I))
    }
    for stage in stages:
        reference = re.match(r"FROM\s+(?:--\S+\s+)*(\S+)", stage[0], re.I)
        assert reference is not None
        image = reference.group(1)
        if image.lower() in aliases:
            continue
        name = image.split("@")[0].rsplit(":", 1)[0] if "/" in image else image
        if name not in (WOLFI, UV) or "@sha256:" not in image:
            problems.append(f"builds from {image}, which is not a base pinned by digest")
    final = stages[-1]
    for instruction in final:
        if instruction.split(None, 1)[0].upper() != "COPY":
            continue
        origin, sources = _copy_sources(instruction)
        for source in (s.rstrip("/") for s in sources):
            if origin is not None and source not in FINAL_COPIES_FROM_BUILDER:
                problems.append(f"the final stage copies {source} from {origin}")
            if origin is None and source not in FINAL_COPIES_FROM_CONTEXT:
                problems.append(f"the final stage copies {source} from the build context")
    installs = [i for i in _instructions(text) if re.search(r"litellm\[[^\]]*\]==", i)]
    if len(installs) != 1:
        problems.append("does not install litellm in one step with its extras and its version")
    for install in installs:
        found = re.search(r"litellm\[([^\]]+)\]==1\.101\.0(?![\w.])", install)
        if not found or set(found.group(1).split(",")) != EXTRAS:
            problems.append(
                "does not install litellm 1.101.0 with exactly the pinned image's extras"
            )
        if "litellm-proxy-extras==0.4.94" not in install:
            problems.append("does not pin litellm-proxy-extras 0.4.94 beside it")
        if not re.search(r"--override\s+\S*overrides\.txt", install):
            problems.append(
                "the install does not take the override that keeps the proprietary package out"
            )
        if not re.search(r"(--constraints?|-c)\s+\S*constraints\.txt", install):
            problems.append("the install does not hold every other package to the constraints file")
    for number, stage in ((0, stages[-2]), (1, final)):
        place = "builder" if number == 0 else "final"
        gate = [i for i in stage if "licence_gate.py" in i and i.upper().startswith("RUN ")]
        if not gate:
            problems.append(f"the {place} stage does not run the licence gate")
    if final_user(text) != "10001:10001":
        problems.append("does not end as the numeric user 10001:10001")
    return problems


def constraints_problems(text: str) -> list[str]:
    """Why a constraints file could carry the commercial package or hold too little."""
    problems = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if re.search(r"enterprise", text, re.I):
        problems.append("names the commercially licensed package or folder")
    loose = [ln for ln in lines if not re.fullmatch(r"[A-Za-z0-9._-]+==[A-Za-z0-9._+!-]+", ln)]
    if loose:
        problems.append(f"holds a line that is not an exact pin: {loose[0]!r}")
    if len(lines) < 100:
        problems.append("holds fewer than the hundred packages the pinned image's venv has")
    return problems


def overrides_problems(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    return [] if lines == [OVERRIDE_LINE] else ["is not the one line that removes the package"]


def test_the_gateways_folder_holds_its_files() -> None:
    for name in (
        "Dockerfile", "constraints.txt", "overrides.txt", "licence_gate.py", "NOTICE",
        "docker/prod_entrypoint.sh", "docker/entrypoint.sh",
    ):  # fmt: skip
        assert (FOLDER / name).is_file(), f"deploy/litellm/{name} is missing"


def test_the_real_dockerfile_cannot_carry_the_commercial_folder_or_package() -> None:
    assert dockerfile_problems(_read(FOLDER / "Dockerfile")) == []


def test_the_real_constraints_file_holds_the_venv_without_the_commercial_package() -> None:
    assert constraints_problems(_read(FOLDER / "constraints.txt")) == []


def test_the_real_override_is_the_one_line_that_removes_the_package() -> None:
    assert overrides_problems(_read(FOLDER / "overrides.txt")) == []


@pytest.mark.parametrize(
    ("plant", "expected"),
    [
        # The publisher's own lines (Dockerfile at revision 18243cd7), added as they stand.
        (lambda t: t + "COPY --from=builder /app/enterprise /app/enterprise\n", "commercially"),
        (lambda t: t + "COPY --from=builder /app/litellm-proxy-extras /app/litellm-proxy-extras\n",
         "the final stage copies /app/litellm-proxy-extras"),
        (lambda t: t + "COPY --from=builder /app /app\n", "the final stage copies /app from"),
        (lambda t: t + "COPY . /app\n", "the final stage copies . from the build context"),
        # Derived from the publisher's image (its later `rm` would hide the folder, not remove it).
        (lambda t: f"FROM {PUBLISHERS_IMAGE}\n" + t, "which is not a base pinned by digest"),
        (lambda t: t.replace("--override overrides.txt", ""), "does not take the override"),
        (lambda t: t.replace("--constraint constraints.txt", ""), "constraints file"),
        (lambda t: t.replace("litellm-proxy-extras==0.4.94", "litellm-proxy-extras"), "0.4.94"),
        (lambda t: t.replace("saml,", ""), "exactly the pinned image's extras"),
        (lambda t: re.sub(r"(?m)^RUN[^\n]*licence_gate\.py[^\n]*\n", "", t), "licence gate"),
        (lambda t: t.replace("USER 10001:10001", "USER root"), "numeric user"),
    ],
    ids=[
        "copies-the-folder", "copies-another-tree", "copies-all-of-app", "copies-the-context",
        "derived-from-the-publishers-image", "no-override", "no-constraints", "extras-unpinned",
        "extra-dropped", "gate-dropped", "root",
    ],
)  # fmt: skip
def test_a_fault_planted_in_the_real_dockerfile_is_refused(plant: object, expected: str) -> None:
    real = _read(FOLDER / "Dockerfile")
    planted = plant(real)  # type: ignore[operator]
    assert planted != real
    assert any(expected in p for p in dockerfile_problems(planted)), dockerfile_problems(planted)


def test_a_gate_stage_of_the_final_image_alone_is_refused() -> None:
    """The gate in the builder alone does not cover what the final stage copies in: each stage's own
    run is held (the builder's was dropped above; the final stage's here)."""
    real = _read(FOLDER / "Dockerfile")
    stages = real.split("\nFROM ")
    assert len(stages) >= 3, "the uv image, the builder and the final stage"
    last = re.sub(r"(?m)^RUN[^\n]*licence_gate\.py[^\n]*\n", "", stages[-1])
    planted = "\nFROM ".join([*stages[:-1], last])
    assert planted != real
    assert any(
        "final stage does not run the licence gate" in p for p in dockerfile_problems(planted)
    )


@pytest.mark.parametrize(
    "line",
    [
        "litellm-enterprise==0.1.65",  # the pinned image's `pip freeze`, as it prints it
        "litellm-enterprise @ file:///app/enterprise",  # its venv's direct URL (scout row 3)
        "litellm_enterprise-0.1.65-py3-none-any.whl",  # the archives beside the folder
        "fastapi>=0.1",
    ],
    ids=["freeze-line", "direct-url", "archive", "unpinned"],
)
def test_a_line_planted_in_the_real_constraints_file_is_refused(line: str) -> None:
    real = _read(FOLDER / "constraints.txt")
    assert constraints_problems(real + line + "\n"), line


def test_the_constraints_file_planted_empty_is_refused() -> None:
    assert any("fewer than" in p for p in constraints_problems("fastapi==0.1\n"))


def test_an_override_planted_away_is_refused() -> None:
    real = _read(FOLDER / "overrides.txt")
    assert overrides_problems(real.replace("litellm-enterprise", "litellm-proxy-extras"))
    assert overrides_problems("")
    assert overrides_problems(real + "fastapi==0.1\n")


def test_the_vendored_entrypoint_scripts_are_the_publishers_byte_for_byte() -> None:
    for name, expected in ENTRYPOINT_SHA256.items():
        path = FOLDER / "docker" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    notice = _read(FOLDER / "NOTICE")
    assert "MIT" in notice and "18243cd7" in notice
    # A plant: one byte changed is not the file.
    tampered = (FOLDER / "docker" / "prod_entrypoint.sh").read_bytes() + b"\n"
    assert hashlib.sha256(tampered).hexdigest() != ENTRYPOINT_SHA256["prod_entrypoint.sh"]


# --- the build's licence gate -------------------------------------------------------------------


def _gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pl13b_licence_gate", FOLDER / "licence_gate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _distribution(
    site: Path, name: str, version: str, *headers: str, folder: str | None = None
) -> None:
    """An installed distribution as the installer leaves it: `<name>-<version>.dist-info/METADATA`
    (the headers a build backend writes) and, when asked, the package's own folder."""
    info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    lines = ["Metadata-Version: 2.4", f"Name: {name}", f"Version: {version}", *headers]
    (info / "METADATA").write_text("\n".join(lines) + "\n\nA description.\n", encoding="utf-8")
    if folder:
        (site / folder).mkdir()
        (site / folder / "__init__.py").write_text("", encoding="utf-8")


def _clean_site(tmp_path: Path) -> Path:
    site = tmp_path / "site-packages"
    site.mkdir()
    _distribution(site, "litellm", "1.101.0", "License-Expression: MIT", folder="litellm")
    _distribution(site, "psycopg", "3.3.4", "License-Expression: LGPL-3.0-only", folder="psycopg")
    _distribution(
        site, "detect-secrets", "1.5.0", "License: UNKNOWN",
        "Classifier: License :: OSI Approved :: Apache Software License",
    )  # fmt: skip
    _distribution(site, "aurelio-sdk", "0.0.19")  # declares nothing: the gate is not default-deny
    return site


def test_the_gate_passes_an_ordinary_venv(tmp_path: Path) -> None:
    assert _gate().check(_clean_site(tmp_path)) == []


def test_the_gate_fails_the_commercial_package_as_its_own_metadata_declares_it(
    tmp_path: Path,
) -> None:
    site = _clean_site(tmp_path)
    _distribution(
        site, "litellm-enterprise", "0.1.65", "License-Expression: LicenseRef-Proprietary",
        "License-File: LICENSE.md", folder="litellm_enterprise",
    )  # fmt: skip
    problems = _gate().check(site)
    assert problems and any("litellm-enterprise" in p for p in problems)
    assert _gate().main([str(site)]) == 1


def test_the_gate_fails_another_proprietary_distribution_by_its_licence_alone(
    tmp_path: Path,
) -> None:
    """Not only the one package by name: a distribution under another name, declaring the same."""
    site = _clean_site(tmp_path)
    _distribution(site, "some-other-pkg", "2.0", "License-Expression: LicenseRef-Proprietary")
    assert any("some-other-pkg" in p for p in _gate().check(site))


@pytest.mark.parametrize(
    "header",
    [
        "License: Proprietary",
        "Classifier: License :: Other/Proprietary License",
        "License-Expression: MIT AND LicenseRef-Proprietary",  # the shape a dual declaration takes
    ],
    ids=["old-field", "classifier", "and-expression"],
)
def test_the_gate_reads_every_way_a_distribution_declares_a_proprietary_licence(
    tmp_path: Path, header: str
) -> None:
    site = _clean_site(tmp_path)
    _distribution(site, "another-one", "1.0", header)
    assert any("another-one" in p for p in _gate().check(site))


def test_the_gate_fails_the_package_by_name_whatever_it_declares(tmp_path: Path) -> None:
    """The name rule on its own: a package of that name declaring MIT is still refused."""
    site = _clean_site(tmp_path)
    _distribution(site, "litellm-enterprise", "0.1.65", "License-Expression: MIT")
    assert any("litellm-enterprise" in p for p in _gate().check(site))


def test_the_gate_fails_a_copy_of_the_packages_folder_with_no_metadata(tmp_path: Path) -> None:
    site = _clean_site(tmp_path)
    (site / "litellm_enterprise").mkdir()
    (site / "litellm_enterprise" / "__init__.py").write_text("", encoding="utf-8")
    assert any("litellm_enterprise" in p for p in _gate().check(site))


def test_the_gate_fails_the_commercial_folder_in_the_app_root(tmp_path: Path) -> None:
    site = _clean_site(tmp_path)
    app = tmp_path / "app"
    (app / "enterprise" / "enterprise_hooks").mkdir(parents=True)
    (app / "enterprise" / "LICENSE.md").write_text("The BerriAI Enterprise license\n")
    assert _gate().check(site, app) != []
    assert _gate().check(site, tmp_path / "an-empty-app") == []
    assert _gate().main([str(site), "--app", str(app)]) == 1


def test_the_dockerfile_runs_the_gate_over_the_installed_venv_and_the_app_root() -> None:
    """The gate is the build's own check (the ner image's pattern): it runs after the install, in
    the builder, and again in the final image over what was copied in, and is not left there."""
    text = _read(FOLDER / "Dockerfile")
    builder, final = _stages(text)[-2], _stages(text)[-1]
    install = next(i for i, s in enumerate(builder) if re.search(r"litellm\[[^\]]*\]==", s))
    gate = next(i for i, s in enumerate(builder) if "licence_gate.py" in s and s.startswith("RUN"))
    assert gate > install, "the gate runs before the install it is there to check"
    assert any("--app" in s for s in final if "licence_gate.py" in s and s.startswith("RUN"))
    assert any(re.search(r"\brm\b[^\n]*licence_gate\.py", s) for s in final), "left in the image"


# --- the renderer: the gateway is ours, and gets no environment file ------------------------------


def _config(source_path: str | None) -> OspreyConfig:
    loaded = OspreyConfig.model_validate({"profile": "local-lite"})
    return loaded.model_copy(
        update={"components": loaded.components.model_copy(update={"source_path": source_path})}
    )


def _resolver(image: str) -> str:
    return image.partition("@")[2] or "sha256:" + hashlib.sha256(image.encode()).hexdigest()


def _gateway(source_path: str | None, **kwargs: str) -> dict:
    result = render(_config(source_path), resolver=_resolver, **kwargs)
    return yaml.safe_load(result.artefacts["compose.yaml"])["services"]["litellm"]


def gateway_problems(service: dict, *, building: bool) -> list[str]:
    """Why a rendered gateway is not "built by us, no environment file, otherwise as before"."""
    problems = []
    if "env_file" in service:
        problems.append("reads an environment file (the whole deployment's secrets)")
    image = str(service.get("image"))
    if "berriai" in image:
        problems.append(f"runs the publisher's image {image}")
    elif building and image != "osprey/litellm:local":
        problems.append(f"does not run the image this checkout builds ({image})")
    elif not building and not re.fullmatch(r"ghcr\.io/ospreyflow/litellm:[0-9a-z]+", image):
        problems.append(f"does not run our release's image ({image})")
    if building != ("build" in service):
        problems.append("builds exactly when the render is from source")
    rest = {k: v for k, v in service.items() if k not in ("image", "build")}
    if rest != GATEWAY_STANZA:
        problems.append("the rest of the stanza is not what it was before")
    return problems


def test_the_gateway_is_our_image_with_no_env_file_in_a_pull_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OSPREY_IMAGE_REGISTRY", raising=False)
    service = _gateway(None)
    assert gateway_problems(service, building=False) == []
    assert service["image"] == f"ghcr.io/ospreyflow/litellm:{git_sha()}"


def test_the_gateway_is_built_from_its_own_folder_in_a_render_from_source() -> None:
    service = _gateway(str(CORE))
    assert gateway_problems(service, building=True) == []
    # A checkout-rooted deployment (`deploy/generated/<name>/`): the folder is three levels up.
    assert service["build"] == {"context": "../../../deploy/litellm", "dockerfile": "Dockerfile"}


def test_a_deployment_kept_by_name_builds_the_gateway_from_the_checkouts_own_folder() -> None:
    checkout = "/srv/ospreyflow-checkout"  # where the named deployment's checkout is, not this one
    config = _config(str(CORE))
    images = service_images(config, build_context=checkout)
    gateway = next(i for i in images if i.service == "litellm")
    assert gateway.owned and gateway.dockerfile == DOCKERFILE_PATH
    result = render(config, resolver=_resolver, build_context=checkout)
    rendered = yaml.safe_load(result.artefacts["compose.yaml"])["services"]["litellm"]
    assert rendered["build"] == {
        "context": f"{checkout}/deploy/litellm",
        "dockerfile": "Dockerfile",
    }


def test_the_other_owned_services_still_read_the_deployments_env_file() -> None:
    """The gateway's opt-out is its own: it does not change the services that need the file (the
    Conduit fail-fasts on a missing `OIDC_JWKS_URL` without it)."""
    result = render(_config(str(CORE)), resolver=_resolver)
    services = yaml.safe_load(result.artefacts["compose.yaml"])["services"]
    for name in ("api", "workspace", "ner"):
        assert services[name]["env_file"] == ["deployment.env"], name


@pytest.mark.parametrize("building", [False, True], ids=["pull", "source"])
@pytest.mark.parametrize(
    ("plant", "expected"),
    [
        # What `ServiceImage.owned` gave every owned service: the deployment's whole environment.
        (lambda s: {**s, "env_file": ["deployment.env"]}, "environment file"),
        (lambda s: {**s, "image": PUBLISHERS_IMAGE}, "the publisher's image"),
        (lambda s: {**s, "environment": {**s["environment"], "OSPREY_OTHER": "x"}}, "the rest"),
        (lambda s: {**s, "volumes": [*s["volumes"], "./deployment.env:/app/.env:ro"]}, "the rest"),
    ],
    ids=["env-file", "publishers-image", "extra-variable", "extra-mount"],
)
def test_a_fault_planted_in_the_rendered_gateway_is_refused(
    plant: object, expected: str, building: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OSPREY_IMAGE_REGISTRY", raising=False)
    real = _gateway(str(CORE) if building else None)
    planted = plant(copy.deepcopy(real))  # type: ignore[operator]
    assert planted != real
    assert any(expected in p for p in gateway_problems(planted, building=building))


def test_the_gateways_keys_are_still_blanked_for_every_other_service_and_given_to_it() -> None:
    """A hosted engine's key is read by the gateway alone (ADR-135 decision 2): the gateway's own
    environment names it, every service that reads the env file blanks it, and the gateway reads no
    env file at all."""
    models = ModelsConfig(
        local_only=False,
        providers=[ModelProviderConfig(name="gemini", roles={"extraction": "gemini-2.5-flash"})],
        defaults={"extraction": "gemini"},
        sendable_handling_codes=["P"],
    )
    config = _config(str(CORE)).model_copy(update={"models": models})
    services = yaml.safe_load(render(config, resolver=_resolver).artefacts["compose.yaml"])[
        "services"
    ]
    gateway = services["litellm"]
    assert "env_file" not in gateway
    assert gateway["environment"]["OSPREY_MODEL_KEY_GEMINI"] == "${OSPREY_MODEL_KEY_GEMINI:-}"
    assert services["api"]["environment"]["OSPREY_MODEL_KEY_GEMINI"] == ""
    # A hosted engine puts the gateway on the egress network too; nothing else of its stanza moves.
    assert gateway["networks"] == ["osprey", "egress"]
    unchanged = ("image", "build", "environment", "networks")
    assert {k: v for k, v in gateway.items() if k not in unchanged} == {
        k: v for k, v in GATEWAY_STANZA.items() if k not in unchanged
    }


# --- the lock -------------------------------------------------------------------------------------


def test_the_lock_names_the_gateway_as_our_image_by_repository_and_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`harness/release_lock.py` is unchanged: the gateway is one more owned image in it."""
    monkeypatch.delenv("OSPREY_IMAGE_REGISTRY", raising=False)
    lock = yaml.safe_load(render_release_lock(OspreyConfig(), _resolver))
    rows = [r for r in lock["images"] if r["service"] == "litellm"]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["repository"] == "ghcr.io/ospreyflow/litellm"
    assert row["tag"] == git_sha()
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", row["digest"])
    assert row["source"] != "reference", (
        "an owned image's digest is the registry's, not a pin in code"
    )
    assert not [r for r in lock["images"] if "berriai" in str(r["repository"])]
    assert sum(i.service == "litellm" for i in release_images(OspreyConfig())) == 1


def test_a_render_from_source_locks_the_gateway_as_a_local_build() -> None:
    result = render(_config(str(CORE)), resolver=_resolver)
    rows = yaml.safe_load(result.artefacts["versions.lock"])["images"]
    row = next(r for r in rows if r["service"] == "litellm")
    assert row["source"] == "local-build" and row["digest"] == "local-build"
    assert row["repository"] == "osprey/litellm"


# --- the pin is the same in every place that holds it ---------------------------------------------


def _wolfi_and_uv_references(text: str) -> list[str]:
    return [
        m.group(1)
        for s in _stages(text)
        if (m := re.match(r"FROM\s+(?:--\S+\s+)*(\S+)", s[0], re.I))
        and m.group(1).split("@")[0].rsplit(":", 1)[0] in (WOLFI, UV)
    ]


def test_both_stages_build_from_the_same_wolfi_digest_the_register_holds() -> None:
    text = _read(FOLDER / "Dockerfile")
    references = _wolfi_and_uv_references(text)
    wolfi = [r for r in references if r.startswith(WOLFI)]
    assert len(wolfi) == 2 and len(set(wolfi)) == 1, "both stages, one digest"
    rows = {r["name"]: r for r in licence_register.load_register()}
    for reference in references:
        name, pin = licence_register.split_image(reference)
        assert name in rows, f"{name} has no row in the register"
        row = rows[name]
        assert row["pin"] == pin
        assert row["kind"] == "image" and row["test"] == "osi-software"
        assert row["status"] == "confirmed" and row["where_read"]
        assert "deploy/litellm/Dockerfile" in row["named_in"]


def test_a_base_digest_that_parts_from_the_registers_is_refused_by_the_register_gate() -> None:
    """The real gate over the real sources, with the Dockerfile's base digest changed in its own
    text: the register names the other one, so the gate fails (the plant takes the Dockerfile's own
    shape, a `FROM` line)."""
    sources = licence_register.read_sources()
    assert DOCKERFILE_PATH in sources, "the register's walk reads the gateway's Dockerfile"
    registered = licence_register.load_register()
    named = licence_register.named_by_code(sources)
    assert licence_register.find_register_violations(registered, named) == []
    planted = dict(sources)
    planted[DOCKERFILE_PATH] = re.sub(
        r"(wolfi-base@sha256:)[0-9a-f]{64}", r"\g<1>" + "0" * 64, sources[DOCKERFILE_PATH]
    )
    assert planted[DOCKERFILE_PATH] != sources[DOCKERFILE_PATH]
    found = licence_register.find_register_violations(
        registered, licence_register.named_by_code(planted)
    )
    assert any("wolfi-base" in v and "pin differs" in v for v in found), found


def test_the_publishers_image_is_no_longer_held_for_the_owner() -> None:
    assert "ghcr.io/berriai/litellm" not in licence_register.HELD_FOR_OWNER


def test_the_gateways_dockerfile_is_the_one_every_place_names() -> None:
    gateway = next(i for i in service_images(OspreyConfig()) if i.service == "litellm")
    assert gateway.owned and gateway.dockerfile == DOCKERFILE_PATH
    # The developer stack builds the same folder (it ran the publisher's image by digest before).
    dev = yaml.safe_load(_read(CORE / "deploy" / "compose" / "dev.yaml"))["services"]["litellm"]
    assert "berriai" not in str(dev.get("image", ""))
    build = dev["build"]
    context = build["context"] if isinstance(build, dict) else build
    assert (CORE / "deploy" / "compose" / context).resolve() == FOLDER.resolve()
    assert (build.get("dockerfile", "Dockerfile") if isinstance(build, dict) else "Dockerfile") == (
        "Dockerfile"
    )
    # The cloud platform builds it the same way, and says so in its manifest.
    profile = yaml.safe_load(_read(CORE / "harness" / "cloud_platform" / "profile.yaml"))
    assert profile["ours"]["litellm"] == {
        "dockerfile": DOCKERFILE_PATH,
        "context": "deploy/litellm",
    }
    manifest = yaml.safe_load(_read(CORE / "harness" / "cloud_platform" / "poc_manifest.yaml"))
    assert manifest["images"]["ospreyflow/litellm"] == {"ours": True, "built_from": DOCKERFILE_PATH}
    assert manifest["workloads"]["litellm"]["image"] == "ospreyflow/litellm"
    assert "berriai/litellm" not in manifest["images"]


@pytest.mark.parametrize(
    "guide",
    [CORE / "docs" / "administration-guide.md", BUILD / "spec" / "10_ADMINISTRATION_GUIDE.md"],
    ids=["core-copy", "spec-copy"],
)
def test_both_copies_of_the_administration_guide_name_our_gateway_image(guide: Path) -> None:
    text = _read(guide)
    assert "| `ospreyflow/litellm` | ours | built from `deploy/litellm/Dockerfile` |" in text
    assert re.search(r"\| litellm \| Deployment \| 1 \| `ospreyflow/litellm` \|", text)
    assert "berriai/litellm" not in text


def test_the_gateway_pin_is_one_version_everywhere_in_its_folder() -> None:
    dockerfile = _read(FOLDER / "Dockerfile")
    assert re.findall(r"litellm\[[^\]]*\]==([0-9.]+)", dockerfile) == ["1.101.0"]
    assert re.findall(r"litellm-proxy-extras==([0-9.]+)", dockerfile) == ["0.4.94"]
    notice = _read(FOLDER / "NOTICE")
    assert "1.101.0" in notice
    for name in ("litellm", "litellm-proxy-extras", "litellm-enterprise"):
        # Held by the install line and the override, never by the constraints.
        assert not re.search(rf"(?im)^{name}==", _read(FOLDER / "constraints.txt")), name


# --- no product file names the publisher's image --------------------------------------------------

#: The image's name as a file would write it, but not a link to the project's source repository
#: (the NOTICE may cite where its MIT files came from).
PUBLISHERS_NAME = re.compile(r"(?<!github\.com/)berriai/litellm", re.I)


def files_naming_the_publishers_image(root: Path, files: list[str]) -> list[str]:
    found = []
    for name in files:
        path = root / name
        if path.is_file() and PUBLISHERS_NAME.search(path.read_bytes().decode("utf-8", "ignore")):
            found.append(name)
    return found


def _tracked_files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=CORE, check=True, capture_output=True, text=True
    ).stdout
    return [name for name in listed.split("\0") if name]


def test_no_product_file_names_the_publishers_image() -> None:
    assert files_naming_the_publishers_image(CORE, _tracked_files()) == []


@pytest.mark.parametrize(
    "line",
    [
        f"    image: {PUBLISHERS_IMAGE}",  # dev.yaml's own line
        '            "ghcr.io/berriai/litellm@sha256:d295634e09c648dcdb72c4cc2dd226f5fb87823a73e88c'
        'deb044b",',  # render.py's own
        '  berriai/litellm: {ours: false, upstream: "ghcr.io/berriai/litellm"}',  # the manifest's
        "| litellm | Deployment | 1 | `berriai/litellm` | 250m / 500m |",  # the guide's
    ],
    ids=["compose", "renderer", "manifest", "guide"],
)
def test_a_file_planted_with_the_publishers_image_is_found(tmp_path: Path, line: str) -> None:
    (tmp_path / "harness").mkdir()
    (tmp_path / "harness" / "clean.py").write_text("IMAGE = 'ghcr.io/ospreyflow/litellm'\n")
    (tmp_path / "harness" / "planted.txt").write_text(f"x\n{line}\n")
    (tmp_path / "harness" / "source-link.md").write_text(
        "from https://github.com/BerriAI/litellm\n"
    )
    assert files_naming_the_publishers_image(
        tmp_path, ["harness/clean.py", "harness/planted.txt", "harness/source-link.md"]
    ) == ["harness/planted.txt"]


def test_the_publishers_name_is_no_longer_held_while_the_product_names_it() -> None:
    """The one-way rule: the name leaves `HELD_FOR_OWNER` only once nothing in the product names
    it. Both halves are asserted above; this ties them, so removing the held name first, or naming
    the image again after, fails the same case."""
    held = "ghcr.io/berriai/litellm" in licence_register.HELD_FOR_OWNER
    named = files_naming_the_publishers_image(CORE, _tracked_files())
    assert held or not named, f"the held name is gone but the product still names it in {named}"
    assert not held, "the publisher's image is still held for the owner"
