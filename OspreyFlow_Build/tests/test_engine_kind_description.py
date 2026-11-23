"""The `kind` field's description is the source of the generated types and of the administration
guide's `osprey.yaml` reference, so it must say what `engine_kinds_offered` does (ADR-135 Amendment
14: the organisation's own gateway on every profile, Bedrock on the cloud platform only). AD1a's
verifier found it still saying the gateway was the cloud platform's.

The case that fails if the words drift from the offer (rule 12):
`test_the_kind_description_says_what_each_profile_is_offered`.
"""

from __future__ import annotations

import re
from pathlib import Path

from schemas.deployment import ModelProviderConfig, engine_kinds_offered

REPO = Path(__file__).resolve().parents[2]
GUIDES = [
    REPO / "OspreyFlow_Build" / "spec" / "10_ADMINISTRATION_GUIDE.md",
    REPO / "OspreyFlow_Core" / "docs" / "administration-guide.md",
]


def _kind_words() -> str:
    description = ModelProviderConfig.model_fields["kind"].description
    assert description
    return " ".join(description.split())


def test_the_kind_description_says_what_each_profile_is_offered() -> None:
    words = _kind_words()
    assert set(engine_kinds_offered("small")) == {"provider", "gateway"}
    assert "bedrock" in engine_kinds_offered("cloud-platform")
    assert not re.search(r"cloud-platform only,\s+gateway", words), words
    assert re.search(r"cloud-platform only,\s+bedrock", words), words
    assert "gateway" in words and "every profile" in words


def test_the_guides_reference_rows_say_the_same() -> None:
    words = _kind_words()
    for guide in GUIDES:
        rows = [
            line
            for line in guide.read_text().splitlines()
            if line.startswith(("| `models.provider.kind`", "| `models.providers.kind`"))
        ]
        assert len(rows) == 2, guide
        for row in rows:
            assert words in row, f"{guide.name}: {row}"
