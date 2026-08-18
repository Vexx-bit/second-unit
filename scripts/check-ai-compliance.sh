#!/usr/bin/env bash
# Hackathon compliance guard.
#
# Agentic Cinema rules permit ONLY Google Cloud AI tooling plus the chosen
# partner's products. A single non-Google AI SDK in the dependency tree is a
# Stage One disqualification. AI coding agents reach for these by reflex, so we
# fail the build instead of trusting vigilance.

set -euo pipefail

FORBIDDEN=(
  "openai"
  "anthropic"
  "langchain"
  "langgraph"
  "llama-index"
  "llama_index"
  "crewai"
  "autogen"
  "litellm"
  "transformers"
  "cohere"
  "mistralai"
  "@ai-sdk/"
  "boto3"
  "bedrock"
  "azure-ai"
  "azure.ai"
)

MANIFESTS=$(git ls-files \
  '*requirements*.txt' '*pyproject.toml' '*package.json' '*uv.lock' \
  '*poetry.lock' '*package-lock.json' '*Pipfile' 2>/dev/null || true)

failed=0

if [ -z "$MANIFESTS" ]; then
  echo "No dependency manifests tracked yet — nothing to check."
  exit 0
fi

for term in "${FORBIDDEN[@]}"; do
  # shellcheck disable=SC2086
  if hits=$(grep -rniF -- "$term" $MANIFESTS 2>/dev/null); then
    echo "::error::Forbidden AI dependency '$term' found:"
    echo "$hits"
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  cat <<'EOF'

------------------------------------------------------------------
COMPLIANCE FAILURE

This project may use Google Cloud AI tooling only (google-adk,
google-genai, google-generativeai, google-cloud-aiplatform) plus the
Grafana stack. Any other AI model, agent framework, or AI API is a
hackathon disqualification.

Remove the dependency above. Do not add an exception.
------------------------------------------------------------------
EOF
  exit 1
fi

echo "AI compliance check passed: no forbidden AI dependencies found."
