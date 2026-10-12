"""`python -m ospreyflow` — the command without the installed entry point (the guided install page
runs the install this way, with `PYTHONPATH` at `cli/`)."""

from .main import main

raise SystemExit(main())
