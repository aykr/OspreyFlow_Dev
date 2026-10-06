# The fast recogniser (ADR-098 decision 2): Stanza's English named-entity recogniser on the CPU.
# The model is downloaded here, at build, so a deployment recognises without network access.
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 STANZA_RESOURCES_DIR=/models
WORKDIR /srv

# The CPU build of the runtime: a fraction of the size of the default, which carries GPU libraries.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1
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

COPY services/ner/app.py ./app.py
RUN useradd --create-home --uid 10001 ner && chown -R ner /models /srv
USER ner
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
