"""A rule's files to the standards, exported and imported (`06_DECISIONS.md` ADR-146 decision 3,
"Stored to the standards"; the codec is `packages/rule_standards`). The route module owns the
work; `app.py` owns the wiring, as `watch_routes.py` and `patterns.py` do.

**Export** gives a rule's `.bpmn` and `.dmn`, read through the rules list's own read
(`get_listed`, the reader's dataset reach in its `WHERE`, rule 3), so a rule the reader may not
see is the same 404 as a missing one. Only a rule written in the form is stored to the standards;
a template rule, or a rule that names no dataset (one for the whole deployment, until
`scripts.migrate_rules_to_datasets` makes it one per dataset), is refused in words.

**Import** reads the two files and returns the rule they hold for the editor to open as a draft;
it writes nothing and reads no stored rule, so it can say nothing of any rule the importer may not
see. Each file is capped (`MAX_RULE_FILE_BYTES`) and refused over it before it is parsed. The
declared dataset must be one the importer reads in this case: any other, whether it exists or not,
is the one `dataset_not_found` (rule 3, no existence leak); the case's own analyst layer is not a
dataset a rule declares. The rule's names are then checked
against the model as a sentence's are (`check_sentence`).
"""

from __future__ import annotations

import re

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import Response

from rule_standards import MalformedRuleFile, UnsupportedElements, from_files, to_bpmn, to_dmn
from schemas.domain import OntologySchema, Principal, TypologyRule
from schemas.sentences import SentenceRuleInput, SentenceRuleParams

from .dataset_scope import analyst_layer
from .rule_sentences import check_sentence

#: The most bytes one rule file may hold. The files OspreyFlow writes are a few kilobytes; a
#: drawn area of sixty-four corners stays well under this.
MAX_RULE_FILE_BYTES = 256 * 1024

_MEDIA = {"bpmn": "application/xml", "dmn": "application/xml"}


def _refused(code: int, error: str, detail: str, **more: object) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "detail": detail, **more})


def _file_name(name: str, kind: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "rule"
    return f"{slug[:60]}.{kind}"


def export_rule_file(rule: TypologyRule, kind: str) -> Response:
    """One of the rule's two files, as an attachment."""
    if not isinstance(rule.params, SentenceRuleParams):
        raise _refused(
            422,
            "rule_not_in_the_form",
            "Only a rule written in the form is stored as BPMN and DMN; this rule is a "
            f"{rule.params.typology.replace('_', ' ')} template.",
        )
    if rule.dataset_id is None:
        raise _refused(
            422,
            "rule_names_no_dataset",
            "This rule names no dataset, so it cannot be stored as BPMN and DMN until it is made "
            "one rule per dataset.",
        )
    as_written = SentenceRuleInput(
        name=rule.name,
        sentence=rule.params.sentence,
        budget_ms=rule.budget_ms,
        max_matches=rule.params.max_matches,
    )
    xml = to_bpmn(as_written, dataset_id=rule.dataset_id) if kind == "bpmn" else to_dmn(as_written)
    return Response(
        content=xml,
        media_type=_MEDIA[kind],
        headers={"Content-Disposition": f'attachment; filename="{_file_name(rule.name, kind)}"'},
    )


async def _read_capped(upload: UploadFile, kind: str) -> bytes:
    data = await upload.read(MAX_RULE_FILE_BYTES + 1)
    if len(data) > MAX_RULE_FILE_BYTES:
        raise _refused(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "rule_file_too_large",
            f"The .{kind} file is over {MAX_RULE_FILE_BYTES // 1024} KB, more than any rule "
            "file needs; it was not read.",
        )
    return data


async def import_rule_files(
    bpmn: UploadFile, dmn: UploadFile, *, principal: Principal, ontology: OntologySchema
) -> SentenceRuleInput:
    """The rule the two files hold, checked, written nowhere."""
    bpmn_bytes = await _read_capped(bpmn, "bpmn")
    dmn_bytes = await _read_capped(dmn, "dmn")
    try:
        held = from_files(bpmn_bytes, dmn_bytes)
    except UnsupportedElements as exc:
        raise _refused(422, "rule_file_unsupported", f"{exc}.", unsupported=exc.names) from None
    except MalformedRuleFile as exc:
        raise _refused(422, "rule_file_refused", f"{exc}.") from None
    readable = principal.datasets or []
    if held.dataset_id not in readable or held.dataset_id == analyst_layer():
        raise HTTPException(status_code=404, detail={"error": "dataset_not_found"})
    check_sentence(held.rule.sentence, ontology)
    return held.rule
