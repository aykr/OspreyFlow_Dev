# The fast recogniser (ADR-098 decision 2): Stanza's English named-entity recogniser on the CPU.
# The model is downloaded here, at build, so a deployment recognises without network access.
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 STANZA_RESOURCES_DIR=/models
WORKDIR /srv

# The CPU build of the runtime: a fraction of the size of the default, which carries GPU libraries.
# 2.6.0, not 2.5.1: CVE-2025-32434, a weights-only load that was not (the release scan, 15 October
# 2026). setuptools brought up to date for the same scan (it and the jaraco.context it bundles).
RUN pip install --upgrade setuptools==84.0.0 \
 && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0
COPY services/ner/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
# The licence register (`00_ARCHITECTURE.md` §7) for this image's own packages, which
# `make licence-check` does not see: `licence_gate.py` fails the build on any GPL licence and on any
# it cannot read. Stanza 1.11 and later require udtools (GPL-2.0-or-later); this found it.
COPY services/ner/licence_gate.py ./licence_gate.py
RUN pip install pip-licenses==5.5.5 \
 && python licence_gate.py \
 && pip uninstall -y pip-licenses prettytable wcwidth \
 && rm licence_gate.py
RUN python -c "import stanza; stanza.download('en', processors='tokenize,ner', model_dir='/models')"
# The models are loaded with pickle, so a poisoned one runs code (CVE-2026-54499, which Stanza 1.12.2
# fixes but which needs the GPL udtools; ADR-098 Amendment 5): every file downloaded must be the one
# pinned here, and nothing else may be there. Re-pin only from a build whose files were checked.
COPY services/ner/models.sha256 /tmp/models.sha256
RUN cd /models \
 && sha256sum -c --strict /tmp/models.sha256 \
 && test "$(find . -type f | wc -l)" -eq "$(wc -l < /tmp/models.sha256)" \
 && rm /tmp/models.sha256

COPY services/ner/app.py ./app.py
RUN useradd --create-home --uid 10001 ner && chown -R ner /models /srv
USER ner
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
