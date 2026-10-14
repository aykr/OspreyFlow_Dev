"""The administration guide's `osprey.yaml` reference, made from the deployment's own schema
(`spec/10_ADMINISTRATION_GUIDE.md`, between its `options:begin` and `options:end` markers).

Written from the schema, never by hand, so the guide cannot describe an option that does not exist
or miss one that does: `tests/test_admin_guide.py` fails when the guide's copy differs from what
this prints.

    python -m tools.admin_guide_options          # print the reference
    python -m tools.admin_guide_options --write  # replace the guide's copy
"""

from __future__ import annotations

import argparse
import enum
import re
import sys
import types
import typing
from typing import Any

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from tools.layout import BUILD

GUIDE = BUILD / "spec" / "10_ADMINISTRATION_GUIDE.md"
BEGIN, END = "<!-- options:begin -->", "<!-- options:end -->"


def _models_in(annotation: Any) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for argument in typing.get_args(annotation):
        found += _models_in(argument)
    return found


def _type_name(annotation: Any) -> str:
    if annotation is type(None):
        return "none"
    if isinstance(annotation, type):
        if issubclass(annotation, enum.Enum):
            return " \\| ".join(f"`{member.value}`" for member in annotation)
        if issubclass(annotation, BaseModel):
            return "section"
        return annotation.__name__
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if origin is typing.Literal:
        return " \\| ".join(f"`{value}`" for value in arguments)
    if origin in (typing.Union, types.UnionType):
        return " or ".join(_type_name(a) for a in arguments)
    if origin in (list, tuple, set, frozenset):
        return f"list of {_type_name(arguments[0])}" if arguments else "list"
    if origin is dict:
        return "mapping"
    return str(annotation).replace("typing.", "")


def _default(field: Any) -> str:
    if field.default is PydanticUndefined and field.default_factory is None:
        return "required"
    if field.default_factory is not None:
        return "—"
    value = field.default
    if isinstance(value, enum.Enum):
        value = value.value
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    return f"`{value}`" if value != "" else '""'


#: "Default: <value>." or "Default: <value> —" at the start: the default has its own column.
_DEFAULT_SAID = re.compile(r"^Default: .*?(?:\.\s|—\s*|\.$|$)")
#: A citation of the specification or a decision, which an operator's guide has no use for.
_CITATION = re.compile(r"\s*\((?:[^()]*?(?:\d\d_[A-Z_]+\.md|ADR-\d+)[^()]*?)\)|ADR-\d+: ")

#: Each section's line in the table (a section is a heading, not a setting).
SECTIONS = {
    "components": "Which stores the deployment runs, and where their data lives.",
    "components.storage": "Folders: inside the containers, and on the host for ingest and tiles.",
    "models": "The local models, and a client's own model provider if one is chosen.",
    "models.provider": "A client's own model provider, reached through the deployment's gateway.",
    "governance": "Identity, handling, ontology and the marking shown on screen.",
    "cluster": "A Kubernetes deployment: its namespace, storage classes and machines.",
    "cluster.hosts": "One machine.",
    "network": "The address the deployment answers at, and what it publishes.",
    "map": "The basemaps the map offers.",
    "map.providers": "One basemap.",
    "map.providers.licence": "The basemap's licence.",
    "map.providers.cache": "Keeping fetched tiles a while (online providers only).",
    "reporting": "Dashboards for the business: report sync and Superset.",
    "mail": "A mail server, for invitations and password resets by email.",
    "welcome": "The welcome page before sign-in: its About section and footer links.",
    "external": "What a cloud runs for the deployment instead of a container (Small).",
    "external.postgres": "A cloud's managed PostgreSQL; its password arrives at install.",
    "external.object_store": "A cloud's S3, for every S3-protocol store (AWS).",
    "external.media": "Media on Azure Blob; its key arrives at install.",
    "external.valkey": "A cloud's managed Valkey or Redis (cluster only).",
    "external.search": "A cloud's managed OpenSearch (cluster on AWS only).",
}


def _words(text: str | None) -> str:
    """One line for the table: the default is in its own column, so a leading "Default: …" goes."""
    said = _CITATION.sub("", _DEFAULT_SAID.sub("", " ".join((text or "").split())))
    return said[:1].upper() + said[1:] if said else ""


def rows(model: type[BaseModel], prefix: str = "") -> list[str]:
    lines: list[str] = []
    for name, field in model.model_fields.items():
        path = f"{prefix}{field.alias or name}"
        children = _models_in(field.annotation)
        said = SECTIONS[path] if children else _words(field.description)
        lines.append(
            f"| `{path}` | {_type_name(field.annotation)} | {_default(field)} | "
            f"{said.replace('|', '\\|')} |"
        )
        for child in children:
            lines += rows(child, f"{path}.")
    return lines


def reference() -> str:
    from schemas.deployment import OspreyConfig

    header = ["| Option | Value | Default | What it does |", "| --- | --- | --- | --- |"]
    return "\n".join(header + rows(OspreyConfig)) + "\n"


def guide_copy(text: str) -> str:
    start, end = text.index(BEGIN) + len(BEGIN), text.index(END)
    return text[start:end].strip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.admin_guide_options", description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    made = reference()
    if not args.write:
        sys.stdout.write(made)
        return 0
    text = GUIDE.read_text(encoding="utf-8")
    start, end = text.index(BEGIN) + len(BEGIN), text.index(END)
    GUIDE.write_text(text[:start] + "\n" + made + text[end:], encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
