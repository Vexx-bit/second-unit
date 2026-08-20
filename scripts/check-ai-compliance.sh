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

SECRET_PATTERNS=(
  'glsa_[0-9A-Za-z_-]{32,}'
  'glc_[0-9A-Za-z_-]{32,}'
  'AIza[0-9A-Za-z_-]{35}'
  'github_pat_[0-9A-Za-z_-]{22,}'
)

ALL_TRACKED=$(git ls-files)
for pattern in "${SECRET_PATTERNS[@]}"; do
  # shellcheck disable=SC2086
  if hits=$(grep -rnE -- "$pattern" $ALL_TRACKED 2>/dev/null); then
    echo "::error::Secret pattern '$pattern' found in tracked files:"
    echo "$hits"
    failed=1
  fi
done

JSON_FILES=$(git ls-files '*.json' 2>/dev/null || true)
if [ -n "$JSON_FILES" ]; then
  # shellcheck disable=SC2086
  if hits=$(grep -rniE -- '(private_key|type":\s*"service_account)' $JSON_FILES 2>/dev/null); then
    echo "::error::Service account key material detected in tracked JSON files:"
    echo "$hits"
    failed=1
  fi
fi

if [ "$failed" -ne 0 ]; then
  cat <<'EOF'

------------------------------------------------------------------
COMPLIANCE / SECRET SCAN FAILURE

Forbidden AI dependencies or secrets were detected in tracked files.
Remove secrets and unpermitted dependencies immediately.
------------------------------------------------------------------
EOF
  exit 1
fi

echo "AI compliance and secret checks passed: no forbidden AI dependencies or secrets found."
