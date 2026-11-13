# rules-b HANDOFF · v052D (BRIEF_v052D.md), D(i)+D(ii) · paused 13 Nov (move to the ayan account)
Branch lane/rules-b-v052D from main 7181477. No code written; no stack, no runs alive. Guides step merged (8f95d5a).
Reserved (orchestrator): ADR-098 Am 7, ADR-129 Am 4, ADR-135 Am 12, ADR-144 Am 4. Interim accepted: "Whole case"
disabled with its reason until D(iii); server refuses read_from=case 422 `read_from_unavailable` {detail: words}.
Q3/Q4 already answered to the orchestrator (do not redo): Q4 = `QuestionsService._documents` drops a Document with no
reader text (image) silently -> 0 docs -> no_documents; Q3 = picker hidden <2 extraction engines, fetch failure = [].
Design worked out (build it, tests red first):
- questions.py: `read_from: Literal["selection","graph","case"] | None` on AskRequest (None = selection if any selected,
  else graph). Documents = Document nodes in `scope_of(...)` (selection+one hop, or whole view/the view). Remove
  NoDocumentsError + app.py handler (~3508); with 0 docs a no-documents instruction (answer from links/events, cited and
  entities empty). Empty scope -> 422 `nothing_to_read`. Count docs with no text separately ("1 document has no text to read").
- ReadSummary (packages/schemas, own commit LAST on branch): read_from, documents, documents_without_text, items
  (non-Document nodes), links, events, selected, first_selected (display_name). On QuestionAnswer + QuestionEntry
  (+ `read JSONB` nullable column, PostgresQuestionStore, test_questions_store.py live round-trip). History already hides
  an entry unless reader sees all graph_node_ids (scope nodes incl. no-text docs) -> counts safe (rule 3).
- `POST /v1/investigations/{id}/questions/will-read` (same deps as ask: ASK_MODEL + Editor): read summary, the answering
  engine via RoutedModel.choose on the real material (shared_handling, ids_of_case), unusable engines with reasons
  (routes.offered(named datasets, held) + no extraction model + handling not sendable), refusal words. 409 limit passes
  through. Rows: test_route_rights.py ("ask_model"), test_investigation_levels.py (E).
- Panel (questions/**): radios Selected items / Everything on the graph / Whole case (fieldset "Read from"); "About:
  <first> and N other(s)" / "About: everything on the graph"; "Will read: …" from server; "Will be answered by <label>";
  unusable engines + reasons; per-answer "Read: …" ("No documents were read: the answer comes from the links and events").
  engines.tsx: EngineChoice gains `failed`; panel says the list failed, never none; EnginePicker `reasons` prop.
- Bar (case lane's canvas, a DIFF to orchestrator): SelectionBar shows "Ask the model about these…" whenever something is
  selected (not only documents); GlassCanvas.tsx:3305 view name "Questions on n items".
- Tests: rule-4 (hidden doc/node not counted, quoted or cited, in will-read and ask); QuestionsPanel.test.tsx;
  keyboard/questions.spec.ts new ids (radios, will-read, engine) as a QUESTIONS_ACTIONS diff; axe both looks.
- Spec: 03 §questions line 513, ADR-098 Am 2 point 2 superseded by Am 7. Stages under v052-ask in progress.tsv/heartbeat.
Next session must not redo: the reading/reconciliation above; reservations are granted.
