"""A public dataset's manifest (`06_DECISIONS.md` ADR-138 decision 3).

`ospreyflow demo add public --file <path> --manifest <dataset.yaml>` adds a dataset the
administrator downloaded themselves. The manifest says what the dataset is, where it comes from, on
what terms, the exact file (by SHA-256), whether it holds real people's data, and the Ingest Studio
recipe that loads it. OspreyFlow ships manifests and recipes, never the data (as with PaySim).

    id: vast-2012-mc2
    name: "VAST Challenge 2012, Mini-Challenge 2: Bank of Money regional network (firewall log)"
    source_page: https://www.cs.umd.edu/hcil/varepository/...
    licence: "No licence stated on the source page ..."
    citation: "VAST Challenge 2012 ..."
    redistribution: not_stated       # allowed | forbidden | not_stated
    commercial_use: not_stated       # allowed | forbidden | not_stated
    fictional: true
    real_personal_data: false
    file: {name: Firewall-04072012.csv, sha256: <64 hex>, delimiter: ","}
    recipe: vast_2012_mc2_firewall_recipe.yaml   # beside the manifest, or a shipped recipe's file
    domains: [stix]                  # ADR-126: the packs its case is set to

**Fails closed.** Unknown keys are refused by name. A fictional dataset that also declares real
personal data is refused (one of the two is wrong). The Glass does not read a manifest, so no
TypeScript is generated for it.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.domain import DomainPack

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
Terms = Literal["allowed", "forbidden", "not_stated"]


class PublicDatasetFile(BaseModel):
    """The one file a dataset is loaded from, exactly."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="The file's name as the source publishes it.")
    sha256: str | None = Field(
        description="Its SHA-256, 64 lowercase hex digits; null in a catalogue entry nobody has "
        "pinned yet, which is refused until it is (ADR-138 Amendment 1)."
    )
    size_bytes: int | None = Field(default=None, ge=0, description="Its size, when known.")
    delimiter: str = Field(default=",", min_length=1, max_length=1, description="CSV delimiter.")
    encoding: str = Field(default="utf-8", description="The text encoding to read it with.")

    @field_validator("sha256")
    @classmethod
    def _a_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.match(value):
            raise ValueError("file.sha256 is 64 lowercase hexadecimal digits")
        return value

    @field_validator("name")
    @classmethod
    def _a_bare_name(cls, value: str) -> str:
        if "/" in value or "\\" in value or value in (".", ".."):
            raise ValueError("file.name is the file's own name, with no folder")
        return value


class PublicDatasetManifest(BaseModel):
    """What a public dataset is and how it loads (the module's docstring)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Lowercase letters, digits and hyphens; names its case's dataset.")
    name: str = Field(min_length=1, description="The dataset's name; its case is named after it.")
    source_page: str = Field(description="Where the administrator downloads it (http or https).")
    licence: str = Field(
        min_length=1,
        description="The licence or terms of use as the source states them, or that none is "
        "stated.",
    )
    licence_url: str | None = Field(default=None, description="Where those terms are stated.")
    citation: str | None = Field(default=None, description="How the source asks to be credited.")
    redistribution: Terms = Field(description="Whether the terms let the data be passed on.")
    commercial_use: Terms = Field(description="Whether the terms allow commercial use.")
    fictional: bool = Field(description="True for a fictional or synthetic scenario.")
    real_personal_data: bool = Field(
        description="True when it holds real people's data: accepted in words before it loads."
    )
    file: PublicDatasetFile
    recipe: str = Field(
        min_length=1,
        description="The Ingest Studio recipe that loads it: a file beside the manifest, or a "
        "shipped recipe's file name.",
    )
    domains: list[DomainPack] = Field(
        default_factory=list, description="ADR-126: the domain packs its case is set to."
    )

    @field_validator("id")
    @classmethod
    def _an_id(cls, value: str) -> str:
        if not _ID.match(value):
            raise ValueError(
                "id is 2 to 48 lowercase letters, digits and hyphens, starting with a letter or "
                "digit"
            )
        return value

    @field_validator("source_page", "licence_url")
    @classmethod
    def _a_web_address(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError(f"{value!r} is not an http(s) address")
        return value

    @field_validator("recipe")
    @classmethod
    def _a_recipe_file(cls, value: str) -> str:
        if not value.endswith((".yaml", ".yml")) or value.startswith("/") or ".." in value:
            raise ValueError("recipe is a .yaml file beside the manifest, named without a folder")
        return value

    @model_validator(mode="after")
    def _fiction_holds_no_real_people(self) -> PublicDatasetManifest:
        if self.fictional and self.real_personal_data:
            raise ValueError(
                "a dataset cannot be fictional and hold real personal data; one of the two is wrong"
            )
        return self
