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

# TODO(part 5): pre-download the NLI entailment model here once the
# verification pipeline depends on `transformers`, e.g.:
#   RUN python -c "from transformers import pipeline; \
#       pipeline('text-classification', \
#       model='MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli')"

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /srv
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
