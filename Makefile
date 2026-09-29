# The root Makefile only forwards. The recipes live in `OspreyFlow_Core/Makefile`, because that is
# where the interpreter, `node_modules`, `pyproject.toml` and every path they name are
# (`OspreyFlow_Build/spec/06_DECISIONS.md` ADR-054, Amendment 2). `make launch` from here and
# from `OspreyFlow_Core/` do the same thing.
.DEFAULT_GOAL := help
CORE := OspreyFlow_Core

.PHONY: help
help:
	@$(MAKE) --no-print-directory -C $(CORE) help 2>/dev/null || \
	  echo "Run a target, e.g. 'make launch', 'make ci'; the targets are in $(CORE)/Makefile."

# Any target not named here goes to the product's Makefile, with the same variables.
%:
	@$(MAKE) --no-print-directory -C $(CORE) $@
