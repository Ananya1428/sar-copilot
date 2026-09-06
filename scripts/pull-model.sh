#!/bin/sh
# Pulls the narrative-generation model into the ollama container's model
# store on startup. Idempotent — `ollama pull` is a no-op if the model
# (and its exact quantization tag) is already present.
set -e

MODEL="${LLM_MODEL:-llama3.1:8b-instruct-q4_K_M}"
echo "Pulling ${MODEL} ..."
ollama pull "${MODEL}"
echo "Model pull complete: ${MODEL}"
