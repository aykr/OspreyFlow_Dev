# rules-b · L2.11a · red record

Each plant was made in the code under test, at the call site the import route uses (`from_files` over
bytes `to_bpmn`/`to_dmn` really wrote, with one element or attribute added), run, and then restored
(`diff` clean). The runs were offline on closed ports, with no lease.

## §1 The codec (`packages/rule_standards/codec.py`; `tests/rule_standards/test_codec.py`, 33 cases)

| Plant | Red |
| --- | --- |
| `from_files` never raises `UnsupportedElements` | the BPMN gateway, the DMN element, the `osprey:` element and attribute, and another vendor's attribute (4) |
| attributes not checked | the `osprey:` attribute and the vendor's attribute (2) |
| any `osprey:` element let through | `test_an_unknown_osprey_element_or_attribute_is_refused_by_name` |
| `scope` not written on `osprey:raise` | round trip of *on a hotlist* (just me) and *the whole deployment* |
| any DMN cell read as an equals word | `test_a_dmn_cell_outside_the_forms_written_is_refused` |
| a missing dataset accepted | `test_a_rule_file_naming_no_dataset_is_refused_in_words` |
| sequence flows not checked | `test_the_process_must_be_the_three_elements_in_order` |
| the two files' names not compared | `test_the_two_files_must_be_of_one_rule` |
