#!/usr/bin/env bash
# Deploy Second Unit to Cloud Run.
#
# Prerequisites (once per project):
#   gcloud services enable run.googleapis.com aiplatform.googleapis.com \
#     secretmanager.googleapis.com artifactregistry.googleapis.com \
#     cloudbuild.googleapis.com
#
#   printf '%s' "$GRAFANA_SERVICE_ACCOUNT_TOKEN" | \
#     gcloud secrets create grafana-token --data-file=-
#
#   printf '%s' "$OTEL_EXPORTER_OTLP_HEADERS" | \
#     gcloud secrets create otlp-headers --data-file=-
#
# The Grafana token and the OTLP credentials are Secret Manager secrets, never
# environment variables in the service definition. Cloud Run env vars are visible
# to anyone with view access on the project.

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE="second-unit-agent"
REPO="second-unit"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}"
GRAFANA_URL="${GRAFANA_URL:?set GRAFANA_URL}"

if [[ "${GRAFANA_URL}" == */ ]]; then
  echo "GRAFANA_URL must not end with a slash: ${GRAFANA_URL}" >&2
  exit 1
fi

echo "==> Ensuring Artifact Registry repository exists"
gcloud artifacts repositories describe "${REPO}" \
  --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --description="Second Unit agent images"

echo "==> Building image with Cloud Build"
# Build context is the repo root; the Dockerfile needs agent/.
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}:latest" \
  --file=infra/Dockerfile \
  .

echo "==> Deploying to Cloud Run"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE}:latest" \
  --port=8080 \
  --cpu=2 \
  --memory=2Gi \
  --timeout=900 \
  --min-instances=0 \
  --max-instances=2 \
  --no-allow-unauthenticated \
  --set-env-vars="GRAFANA_URL=${GRAFANA_URL}" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --set-env-vars="GOOGLE_CLOUD_LOCATION=${REGION}" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true" \
  --set-env-vars="OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-}" \
  --set-env-vars="OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf" \
  --set-secrets="GRAFANA_SERVICE_ACCOUNT_TOKEN=grafana-token:latest" \
  --set-secrets="OTEL_EXPORTER_OTLP_HEADERS=otlp-headers:latest"

echo
echo "==> Deployed. The service is NOT public."
echo "Call it with an identity token:"
echo
echo "  URL=\$(gcloud run services describe ${SERVICE} --region=${REGION} \\"
echo "    --project=${PROJECT_ID} --format='value(status.url)')"
echo "  curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" \"\$URL/list-apps\""
echo
echo "For a local UI against the deployed service, use:"
echo "  gcloud run services proxy ${SERVICE} --region=${REGION} --project=${PROJECT_ID}"
