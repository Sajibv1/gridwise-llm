#!/usr/bin/env bash
# Run this from Azure Cloud Shell after publishing the Docker image to GHCR or Docker Hub.
# Do not put API keys in this file, a command history, Git, Docker images, or screenshots.
set -euo pipefail

: "${IMAGE:?Set IMAGE, e.g. ghcr.io/OWNER/gridwise-llm:2026-09-18}"
: "${OPENAI_MODEL:=gpt-5.4-mini-2026-03-17}"
: "${OPENAI_REASONING_EFFORT:=low}"
: "${LLM_SEMANTIC_RETRIES:=1}"

: "${RESOURCE_GROUP:=gridwise-fest-rg}"
: "${ENVIRONMENT:=gridwise-fest-env}"
: "${APP_NAME:=gridwise-api}"

read -r -s -p "OpenAI API key: " OPENAI_API_KEY
echo

az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --image "$IMAGE" \
  --target-port 8000 \
  --ingress external \
  --transport auto \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 2 \
  --secrets "openai-api-key=$OPENAI_API_KEY" \
  --env-vars "OPENAI_API_KEY=secretref:openai-api-key" "OPENAI_MODEL=$OPENAI_MODEL" "OPENAI_REASONING_EFFORT=$OPENAI_REASONING_EFFORT" "LLM_SEMANTIC_RETRIES=$LLM_SEMANTIC_RETRIES" \
  --query properties.configuration.ingress.fqdn \
  --output tsv
