"""A dataset's release as a YAML bundle, written and read (`06_DECISIONS.md` ADR-140 Amendment 9
decision 4; the owner's ruling D4 of 7 November 2026).

`build_bundle` writes the files *Export* gives and `ospreyflow release export` saves; `read_bundle`
checks a bundle before an import plans anything from it. Both are pure: the route reads the stores
and writes the drafts (`services/api/studio_release.py`).

**What a bundle never holds.** Credentials, loaded data, case membership, owners, and the rows of a
licensed screening list. Three things keep them out, and each is a test's planted violation:
- the file models (`schemas.release`) have no field for any of them, and forbid extra keys;
- a screening list's rows are never written, whatever its size (`_rows_travel`);
- every file is scanned before it is returned: a key a credential rides in (`password`, `secret`,
  `token` …) anywhere in a YAML file, or any of the deployment's own secret values (the route passes
  them, read from the environment `deployment.env` fills) anywhere in any file, refuses the export
  in words naming the file, never the value.

A reference list's rows travel only while the list is small (`MAX_LIST_ROWS`); a larger list's rows
are left for the receiving environment to import, and the list's file says so (`rows: null`),
never a cut-down copy (rule 2).
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import yaml
from pydantic import ValidationError

from schemas.dataset_model import ReferenceList, TargetModel
from schemas.ingest import PipelineGraph, PipelineNodeKind, StudioRecipeDraft
from schemas.release import (
    RELEASE_API_VERSION,
    RELEASE_KIND,
    DatasetRelease,
    ReleasedDomainModel,
    ReleasedPipeline,
    ReleasedReferenceList,
    ReleaseFile,
    ReleaseMetadata,
    ReleaseSpec,
)

from .pipeline import pipeline_from_recipe

MANIFEST = "release.yaml"
MODEL_FILE = "model.yaml"
#: A list of more rows than this keeps its rows at home (decision 4: "a small list's rows").
MAX_LIST_ROWS = 10_000
#: A bundle's whole size, read or written: an upload is bounded, never unbounded.
MAX_BUNDLE_BYTES = 32 * 1024 * 1024

#: A mapping key a credential rides in. Matched on the whole key, or its last `_`/`-` part, so
#: `token_column` (a column's name) is not one and `client_secret` is.
_CREDENTIAL_KEY = re.compile(
    r"(?i)^(?:.*[_-])?(password|passwd|secret|token|credentials?|api[_-]?key|private[_-]?key)$"
)
#: A deployment secret shorter than this is not scanned for: it would match ordinary words.
_SHORTEST_SECRET = 8


class ReleaseRefused(ValueError):
    """A bundle that may not be written or read, in words (rule 2): never a partial bundle."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class ListToRelease:
    """A reference list and, for a dataset's own list, its rows (`None` when none are kept)."""

    reference: ReferenceList
    rows: Sequence[Mapping[str, object]] | None = None


@dataclass
class Bundle:
    """A bundle read and checked: the manifest and every file's parsed content."""

    manifest: DatasetRelease
    model: ReleasedDomainModel
    pipelines: list[ReleasedPipeline] = field(default_factory=list)
    lists: list[ReleasedReferenceList] = field(default_factory=list)
    #: Each list's rows by the list's name, for the lists whose rows travelled.
    list_rows: dict[str, list[dict[str, str]]] = field(default_factory=dict)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _yaml(data: Mapping[str, Any]) -> bytes:
    return yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True, width=100).encode()


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "item"


def _rows_travel(item: ListToRelease) -> bool:
    """A dataset's own reference list's rows, while small; never a screening list's (licensed)."""
    return (
        item.reference.kind == "reference"
        and item.rows is not None
        and 0 < len(item.rows) <= MAX_LIST_ROWS
    )


def _csv(rows: Sequence[Mapping[str, object]]) -> bytes:
    columns: list[str] = []
    for row in rows:
        columns.extend(c for c in row if c not in columns)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: "" if row.get(c) is None else str(row.get(c)) for c in columns})
    return out.getvalue().encode()


def _pipeline_of(draft: StudioRecipeDraft) -> ReleasedPipeline:
    graph = pipeline_from_recipe(draft).model_copy(deep=True)
    for node in graph.nodes:
        # The load's dataset is the receiving environment's, set at import.
        if node.kind is PipelineNodeKind.LOAD:
            node.config.pop("dataset_id", None)
    return ReleasedPipeline(
        pipeline_id=draft.recipe_id,
        exported_version=draft.version,
        label=draft.label,
        connector_profile=draft.connector_profile,
        source_location=draft.source_location,
        handling=dict(draft.handling),
        legal_basis=draft.legal_basis,
        row_template=None
        if draft.row_template is None
        else draft.row_template.model_dump(mode="json"),
        deduplicate=None
        if draft.deduplicate is None
        else draft.deduplicate.model_dump(mode="json"),
        pack_versions=draft.pack_versions,
        pipeline=graph.model_dump(mode="json"),
    )


def credential_keys(data: object, where: str = "") -> list[str]:
    """Every mapping key, at any depth, a credential rides in."""
    found: list[str] = []
    if isinstance(data, Mapping):
        for key, value in data.items():
            path = f"{where}.{key}" if where else str(key)
            if isinstance(key, str) and _CREDENTIAL_KEY.match(key):
                found.append(path)
            found.extend(credential_keys(value, path))
    elif isinstance(data, list):
        for i, value in enumerate(data):
            found.extend(credential_keys(value, f"{where}[{i}]"))
    return found


def _scan(files: Mapping[str, bytes], secrets: Collection[str]) -> list[str]:
    problems: list[str] = []
    scanned = [s for s in secrets if len(s) >= _SHORTEST_SECRET]
    for path, data in files.items():
        text = data.decode("utf-8", errors="replace")
        if any(secret in text for secret in scanned):
            problems.append(
                f"{path} holds one of this deployment's secrets, so nothing is exported"
            )
        if path.endswith(".yaml"):
            for key in credential_keys(yaml.safe_load(text)):
                problems.append(f"{path} has a field a credential is kept in ({key})")
    return problems


def build_bundle(
    *,
    name: str,
    version: str,
    model: TargetModel,
    pipelines: Sequence[StudioRecipeDraft],
    lists: Sequence[ListToRelease],
    connections: Collection[str],
    secrets: Collection[str],
) -> dict[str, bytes]:
    """The bundle's files by path, the manifest (`release.yaml`) among them. Refused in words
    (`ReleaseRefused`), with nothing returned, when a file would hold a credential."""
    try:
        metadata = ReleaseMetadata(name=name, version=version)
    except ValidationError as error:
        raise ReleaseRefused(
            [
                "a release's name is lower-case letters, digits, '-' and '.', starting and "
                "ending with a letter or digit; its version is 1 to 64 characters"
            ]
        ) from error
    files: dict[str, bytes] = {}
    roles: dict[str, str] = {}

    released_model = ReleasedDomainModel(
        exported_version=model.version,
        packs={str(k): v for k, v in model.packs.items()},
        extensions=list(model.extensions),
        reference_lists=list(model.reference_lists),
    )
    files[MODEL_FILE] = _yaml(released_model.model_dump(mode="json"))
    roles[MODEL_FILE] = "domain_model"

    pipeline_paths: list[str] = []
    for draft in sorted(pipelines, key=lambda d: (d.label, d.recipe_id)):
        path = f"pipelines/{_slug(draft.label)}-{_slug(draft.recipe_id)[:12]}.yaml"
        files[path] = _yaml(_pipeline_of(draft).model_dump(mode="json"))
        roles[path] = "pipeline"
        pipeline_paths.append(path)

    list_paths: list[str] = []
    for item in sorted(lists, key=lambda i: i.reference.name):
        rows_path: str | None = None
        if _rows_travel(item):
            assert item.rows is not None
            data = _csv(item.rows)
            rows_path = f"lists/rows/{_sha(data)}.csv"
            files[rows_path] = data
            roles[rows_path] = "list_rows"
        ref = item.reference
        released = ReleasedReferenceList(
            id=ref.id,
            name=ref.name,
            kind=ref.kind,
            key_column=ref.key_column,
            version=ref.version,
            schedule=ref.schedule,
            rows=rows_path,
        )
        path = f"lists/{_slug(ref.name)}.yaml"
        files[path] = _yaml(released.model_dump(mode="json"))
        roles[path] = "reference_list"
        list_paths.append(path)

    problems = _scan(files, secrets)
    if problems:
        raise ReleaseRefused(problems)

    manifest = DatasetRelease(
        apiVersion=RELEASE_API_VERSION,  # type: ignore[arg-type]
        kind=RELEASE_KIND,  # type: ignore[arg-type]
        metadata=metadata,
        spec=ReleaseSpec(
            domain_model=MODEL_FILE,
            packs=released_model.packs,
            pipelines=pipeline_paths,
            reference_lists=list_paths,
            connections=sorted(set(connections)),
            files=[
                ReleaseFile(path=p, role=roles[p], sha256=_sha(d))  # type: ignore[arg-type]
                for p, d in sorted(files.items())
            ],
        ),
    )
    files[MANIFEST] = _yaml(manifest.model_dump(mode="json", by_alias=True))
    return files


def _load_yaml(path: str, data: bytes, problems: list[str]) -> Any:
    try:
        return yaml.safe_load(data.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError):
        problems.append(f"{path} is not YAML that can be read")
        return None


def _model(path: str, cls: type[Any], data: Any, problems: list[str]) -> Any:
    try:
        return cls.model_validate(data)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "the file"
        problems.append(f"{path} is not a release's file: {where}: {first['msg']}")
        return None


def read_bundle(files: Mapping[str, bytes]) -> Bundle:
    """A bundle checked whole before anything is planned from it: the manifest is a
    `DatasetRelease`; every file it names is there with its SHA-256; no file is there it does not
    name; each file is its role's; a list's rows are the CSV its name's checksum says; and no file
    holds a field a credential is kept in. Refused in words (`ReleaseRefused`) otherwise."""
    problems: list[str] = []
    if sum(len(d) for d in files.values()) > MAX_BUNDLE_BYTES:
        raise ReleaseRefused([f"the bundle is larger than {MAX_BUNDLE_BYTES // (1024 * 1024)} MB"])
    if MANIFEST not in files:
        raise ReleaseRefused([f"the bundle has no {MANIFEST}"])
    raw = _load_yaml(MANIFEST, files[MANIFEST], problems)
    manifest: DatasetRelease | None = (
        _model(MANIFEST, DatasetRelease, raw, problems) if raw is not None else None
    )
    if manifest is None:
        raise ReleaseRefused(problems)

    named = {f.path: f for f in manifest.spec.files}
    for path in sorted(set(files) - set(named) - {MANIFEST}):
        problems.append(f"{path} is in the bundle but not in its manifest")
    for path, entry in sorted(named.items()):
        if path not in files:
            problems.append(f"{path} is in the manifest but not in the bundle")
        elif _sha(files[path]) != entry.sha256:
            problems.append(f"{path} is not the file the manifest names (its SHA-256 differs)")
    expected = {
        manifest.spec.domain_model: "domain_model",
        **{p: "pipeline" for p in manifest.spec.pipelines},
        **{p: "reference_list" for p in manifest.spec.reference_lists},
    }
    for path, role in expected.items():
        if path in named and named[path].role != role:
            problems.append(f"{path} is listed as {named[path].role}, not as {role}")
        elif path not in named:
            problems.append(f"{path} is in the manifest's spec but not among its files")
    if problems:
        raise ReleaseRefused(problems)

    for path, data in files.items():
        if path.endswith(".yaml"):
            for key in credential_keys(yaml.safe_load(data.decode("utf-8"))):
                problems.append(f"{path} has a field a credential is kept in ({key})")
    if problems:
        raise ReleaseRefused(problems)

    model_data = _load_yaml(manifest.spec.domain_model, files[manifest.spec.domain_model], problems)
    model = _model(manifest.spec.domain_model, ReleasedDomainModel, model_data, problems)
    pipelines = [
        _model(p, ReleasedPipeline, _load_yaml(p, files[p], problems), problems)
        for p in manifest.spec.pipelines
    ]
    lists = [
        _model(p, ReleasedReferenceList, _load_yaml(p, files[p], problems), problems)
        for p in manifest.spec.reference_lists
    ]
    for pipeline in pipelines:
        if pipeline is not None and pipeline.pipeline is not None:
            try:
                PipelineGraph.model_validate(pipeline.pipeline)
            except ValidationError:
                problems.append(f"the pipeline {pipeline.label!r} is not a pipeline graph")
    list_rows: dict[str, list[dict[str, str]]] = {}
    for item in lists:
        if item is None or item.rows is None:
            continue
        if item.kind != "reference":
            problems.append(f"the list {item.name!r} is a screening list; its rows never travel")
            continue
        if item.rows not in named or named[item.rows].role != "list_rows":
            problems.append(f"the list {item.name!r} names rows the manifest does not list")
            continue
        if item.rows != f"lists/rows/{_sha(files[item.rows])}.csv":
            problems.append(f"the list {item.name!r}'s rows are not named by their checksum")
            continue
        rows = list(csv.DictReader(io.StringIO(files[item.rows].decode("utf-8"))))
        if len(rows) > MAX_LIST_ROWS:
            problems.append(f"the list {item.name!r} carries more than {MAX_LIST_ROWS} rows")
            continue
        list_rows[item.name] = rows
    if problems or model is None or None in pipelines or None in lists:
        raise ReleaseRefused(problems or ["the bundle could not be read"])
    return Bundle(
        manifest=manifest,
        model=model,
        pipelines=[p for p in pipelines if p is not None],
        lists=[x for x in lists if x is not None],
        list_rows=list_rows,
    )


def pipeline_for(released: ReleasedPipeline, dataset_id: str) -> PipelineGraph | None:
    """The released pipeline's graph, its load node pointed at the receiving dataset."""
    if released.pipeline is None:
        return None
    graph = PipelineGraph.model_validate(released.pipeline)
    for node in graph.nodes:
        if node.kind is PipelineNodeKind.LOAD:
            node.config["dataset_id"] = dataset_id
    return graph
