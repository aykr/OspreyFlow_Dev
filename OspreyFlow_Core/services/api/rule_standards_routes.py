"""A rule's files to the standards, exported and imported (`06_DECISIONS.md` ADR-146 decision 3,
"Stored to the standards"; the codec is `packages/rule_standards`). The route module owns the
work; `app.py` owns the wiring, as `watch_routes.py` and `patterns.py` do.

**Export** gives a rule's `.bpmn` and `.dmn`, read through the rules list's own read
(`get_listed`, the reader's dataset reach in its `WHERE`, rule 3), so a rule the reader may not
see is the same 404 as a missing one. Only a rule written in the form is stored to the standards;
a template rule, or a rule that names no dataset (one for the whole deployment, until
`scripts.migrate_rules_to_datasets` makes it one per dataset), is refused in words.

**Import** reads the two files, sent as their text, and returns the rule they hold and the dataset
it declares, for the editor to open as a draft; it writes nothing and reads no stored rule, so it
can say nothing of any rule the importer may not see. The body is capped as it streams
(`MAX_RULE_BODY_BYTES`), and each file (`RULE_FILE_MAX_CHARS`) before it is parsed. The declared
dataset must be the case's own, a source or a composite (never its analyst layer, a layer it
borrows, or a drawn dataset): any other, whether it exists or not, is the app's one
`dataset_not_found` (rule 3, no existence leak). The rule's names are then checked against the
model as a sentence's are (`check_sentence`).
"""

from __future__ import annotations

import json
import re

from fastapi import HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError

from rule_standards import (
    MalformedRuleFile,
    StoredRuleFiles,
    UnsupportedElements,
    from_files,
    rule_files,
)
from schemas.domain import OntologySchema, TypologyRule
from schemas.rule_standards import RULE_FILE_MAX_CHARS, ImportedRule, RuleFilesUpload
from schemas.sentences import SentenceRuleInput, SentenceRuleParams

from .datasets import COMPOSITE, SOURCE, DatasetStore, UnknownDatasetEgressError
from .rule_sentences import check_sentence

#: The most bytes the import's body may hold: both files at their cap, with room for JSON's own
#: escaping. Over it, nothing past the cap is read.
MAX_RULE_BODY_BYTES = 4 * 2 * RULE_FILE_MAX_CHARS

_MEDIA = {"bpmn": "application/xml", "dmn": "application/xml"}


def _refused(code: int, error: str, detail: str, **more: object) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": error, "detail": detail, **more})


def _file_name(name: str, kind: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "rule"
    return f"{slug[:60]}.{kind}"


def export_rule_file(
    rule: TypologyRule, kind: str, *, stored: StoredRuleFiles | None = None
) -> Response:
    """One of the rule's two files, as an attachment. `stored` is the version's files as rules'
    save wrote them (ADR-146 Amendment 5), served byte for byte, never rendered again; a rule saved
    before the save wrote them has none, and its files are rendered by the same `rule_files` the
    save calls, so the two cannot differ."""
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
    if stored is None:
        as_written = SentenceRuleInput(
            name=rule.name,
            sentence=rule.params.sentence,
            budget_ms=rule.budget_ms,
            max_matches=rule.params.max_matches,
        )
        try:
            stored = rule_files(as_written, dataset_id=rule.dataset_id)
        except ValueError as exc:
            raise _refused(
                422, "rule_cannot_be_stored", f"This rule cannot be written as DMN: {exc}."
            ) from None
    return Response(
        content=stored.bpmn if kind == "bpmn" else stored.dmn,
        media_type=_MEDIA[kind],
        headers={"Content-Disposition": f'attachment; filename="{_file_name(rule.name, kind)}"'},
    )


class _TooLarge(Exception):
    pass


async def _read_body(request: Request) -> bytes:
    """The request's body, read no further than the cap: a declared length over it is refused
    before anything is read, and a body that runs past it is refused as it streams, so nothing
    over the cap is ever held or spooled."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_RULE_BODY_BYTES:
        raise _TooLarge
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_RULE_BODY_BYTES:
            raise _TooLarge
    return bytes(body)


def _too_large(what: str) -> HTTPException:
    return _refused(
        413,
        "rule_file_too_large",
        f"{what} is over {RULE_FILE_MAX_CHARS // 1024} KB, more than any rule file needs; it was "
        "not read.",
    )


async def import_rule_files(
    request: Request,
    *,
    investigation_id: str,
    datasets: DatasetStore,
    ontology: OntologySchema,
) -> ImportedRule:
    """The rule the two files hold and the dataset it declares, checked, written nowhere."""
    try:
        body = await _read_body(request)
    except _TooLarge:
        raise _too_large("The upload") from None
    try:
        sent = json.loads(body)
    except ValueError:
        raise _refused(
            422, "rule_file_refused", "The upload is not the two files as JSON."
        ) from None
    for kind in ("bpmn", "dmn"):
        text = sent.get(kind) if isinstance(sent, dict) else None
        if isinstance(text, str) and len(text) > RULE_FILE_MAX_CHARS:
            raise _too_large(f"The .{kind} file")
    try:
        files = RuleFilesUpload.model_validate(sent)
    except ValidationError:
        raise _refused(
            422, "rule_file_refused", "The upload needs both files, the .bpmn and the .dmn."
        ) from None
    try:
        held = from_files(files.bpmn.encode(), files.dmn.encode())
    except UnsupportedElements as exc:
        raise _refused(422, "rule_file_unsupported", f"{exc}.", unsupported=exc.names) from None
    except MalformedRuleFile as exc:
        raise _refused(422, "rule_file_refused", f"{exc}.") from None
    # The declared dataset is the case's own, a source or a composite: never its analyst layer, a
    # layer it borrows, or a drawn dataset (on which no rule runs until it is merged). Any other,
    # whether it exists or not, is the app's one missing dataset (rule 3).
    declarable = {
        d.id
        for d in await datasets.chosen_of_case(investigation_id)
        if d.kind in (SOURCE, COMPOSITE)
    }
    if held.dataset_id not in declarable:
        raise UnknownDatasetEgressError(held.dataset_id)
    check_sentence(held.rule.sentence, ontology)
    return ImportedRule(rule=held.rule, dataset_id=held.dataset_id)
