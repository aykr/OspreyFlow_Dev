# The root Makefile only forwards. A target goes to `OspreyFlow_Build/Makefile` when Build has it —
# the gates, the test suites, the release steps — and otherwise to `OspreyFlow_Core/Makefile`, where
# what a user runs lives (`OspreyFlow_Build/spec/06_DECISIONS.md` ADR-054 Amendment 2, ADR-114
# Amendment 2). `make ci` and `make seed-hmp` from here do what they do from each folder.
.DEFAULT_GOAL := help
CORE := OspreyFlow_Core
BUILD := OspreyFlow_Build

.PHONY: help
help:
	@echo "Run a target, e.g. 'make seed-hmp' (in $(CORE)/Makefile) or 'make ci' (in $(BUILD)/Makefile)."

# Any target not named here goes to the folder whose Makefile has it, Build first, with the same
# variables. `make -q` asks Build only whether it has a rule (exit 2 when it has none).
%:
	@$(MAKE) --no-print-directory -C $(BUILD) -q $@ >/dev/null 2>&1; \
	  if [ $$? -eq 2 ]; then $(MAKE) --no-print-directory -C $(CORE) $@; \
	  else $(MAKE) --no-print-directory -C $(BUILD) $@; fi
