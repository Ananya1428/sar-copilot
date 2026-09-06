FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Dependencies installed from requirements.txt (not `pip install .`) so this
# layer caches independently of source changes — the blueprint's §21 snippet
# runs `pip install .` before any source is copied in, which can't resolve
# the local package yet. Deliberate deviation for a working build.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Part 5: pre-download the semantic entailment check's NLI model at build
# time, not at first request — so a container with no outbound network
# access still has a working model (domain/verification/semantic.py loads
# from the same on-disk HF cache either way). If this fails (e.g. building
# offline), the image still builds; semantic.py degrades gracefully at
# runtime (see its module docstring) rather than crashing the pipeline.
RUN python -c "\
from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
name = 'MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli'; \
AutoTokenizer.from_pretrained(name); \
AutoModelForSequenceClassification.from_pretrained(name)" \
    || echo "WARNING: could not pre-download the NLI model at build time; semantic.py will fetch it at runtime or degrade gracefully if that also fails."

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /srv
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
