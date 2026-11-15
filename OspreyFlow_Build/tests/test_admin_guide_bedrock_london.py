"""§6a.9's Bedrock in London (ADR-135 Amendment 7's London rule; the owner's ruling 17 for v0.6.0): the example's model
is one the schema admits, `_BEDROCK_MODEL_ID` in `packages/schemas/deployment.py`, and a model AWS serves in-Region
in London, never a Claude id the region rule would refuse or London no longer serves on demand (rule 12).
"""

from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
BUILD = Path(__file__).resolve().parents[1]


def bedrock_pattern() -> re.Pattern[str]:
    source = (CORE / "packages" / "schemas" / "deployment.py").read_text(encoding="utf-8")
    m = re.search(r'^_BEDROCK_MODEL_ID = re\.compile\(r"([^"]+)"\)$', source, re.MULTILINE)
    assert m, "the schema's _BEDROCK_MODEL_ID"
    return re.compile(m.group(1))


def example_models(text: str) -> list[str]:
    """Each model the guide's Bedrock example names, in the YAML block under `kind: bedrock`."""
    found = []
    for block in re.findall(r"```yaml\n(.*?)```", text, re.DOTALL):
        for engine in re.split(r"\n    - name: ", block):
            if "kind: bedrock" in engine:
                found += re.findall(r"roles: \{[^}]*?: ([^,}\s]+)", engine)
    return found


def refused_as_examples(models: list[str]) -> list[str]:
    pattern = bedrock_pattern()
    return [m for m in models if not pattern.fullmatch(m) or m.startswith("anthropic.")]


def test_the_example_is_a_model_the_schema_admits_and_london_serves() -> None:
    for name, path in (("guide", CORE / "docs" / "administration-guide.md"), ("spec/10", BUILD / "spec" / "10_ADMINISTRATION_GUIDE.md")):
        models = example_models(path.read_text(encoding="utf-8"))
        assert models == ["amazon.nova-pro-v1:0"], (name, models)
        assert refused_as_examples(models) == [], name


def test_a_profile_or_claude_example_is_flagged() -> None:
    """The guide's own example before ruling 17, and an EU profile's id the region rule refuses."""
    assert refused_as_examples(["anthropic.claude-3-haiku-20240307-v1:0", "eu.anthropic.claude-sonnet-5-5-v1:0"]) == [
        "anthropic.claude-3-haiku-20240307-v1:0", "eu.anthropic.claude-sonnet-5-5-v1:0"]  # fmt: skip


def test_the_guide_says_what_bedrock_in_london_means() -> None:
    text = re.sub(r"\s+", " ", (CORE / "docs" / "administration-guide.md").read_text(encoding="utf-8"))
    assert ("**So Bedrock in London means the models AWS serves in-Region there: Amazon Nova and the Titan embeddings, "
            "not current Claude models, which AWS serves from London only through its EU and global profiles. Claude "
            "through AWS's EU profile is not offered in v0.6.0.**") in text  # fmt: skip
    assert "newer Claude models are offered in London only through inference profiles" not in text
