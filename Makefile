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
# variables. Build's rule database (`-pRrq :`, which builds no target and runs no recipe) says
# whether it has a rule. Not `make -q <target>`: that still runs any `$(MAKE)` line under the
# target, and `ci`'s `core-check` is one, so its answer read as "no rule" and `make ci` went to
# Core (`tests/test_core_stands_alone.py`, found 30 October 2026).
%:
	@if $(MAKE) --no-print-directory -C $(BUILD) -pRrq : 2>/dev/null | grep -qx '$@:.*'; \
	  then $(MAKE) --no-print-directory -C $(BUILD) $@; \
	  else $(MAKE) --no-print-directory -C $(CORE) $@; fi
