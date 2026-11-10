"""A rule's files to the standards, BPMN 2.0 and DMN 1.3, as the import route takes and gives them
(`06_DECISIONS.md` ADR-146 decision 3; the codec is `packages/rule_standards`).

TypeScript is generated from these models (`generate_ts.py`); drift fails the build.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.sentences import SentenceRuleInput

#: The most characters one rule file may hold. The files OspreyFlow writes are a few kilobytes; a
#: drawn area of sixty-four corners stays well under this.
RULE_FILE_MAX_CHARS = 256 * 1024


class RuleFilesUpload(BaseModel):
    """The two files of one rule, as their text: what the editor's *Import* sends."""

    bpmn: str = Field(min_length=1, max_length=RULE_FILE_MAX_CHARS)
    dmn: str = Field(min_length=1, max_length=RULE_FILE_MAX_CHARS)


class ImportedRule(BaseModel):
    """What the two files hold, checked and written nowhere: the rule, and the dataset it declares
    (one the case reads, as a source or a composite), for the editor to open as a draft on it."""

    rule: SentenceRuleInput
    dataset_id: str


ALL_MODELS = (RuleFilesUpload, ImportedRule)
