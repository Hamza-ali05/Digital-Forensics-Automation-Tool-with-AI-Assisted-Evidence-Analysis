#!/bin/bash
set -euo pipefail

CONTAINER_NAME="${1:-dfat-ollama-1}"
MODEL="${2:-llama3}"

echo "Setting up $MODEL model for DFAT..."
echo "Container: $CONTAINER_NAME"
echo ""

echo "Pulling $MODEL (this may take several minutes)..."
docker exec "$CONTAINER_NAME" ollama pull "$MODEL"

echo ""
echo "Model pulled. Verifying..."
docker exec "$CONTAINER_NAME" ollama list

echo ""
echo "$MODEL setup complete."
