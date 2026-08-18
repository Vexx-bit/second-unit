.PHONY: help verify-mcp mcp-serve compliance sim inject-incident backfill

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

verify-mcp: ## Smoke test: can we reach Grafana through mcp-grafana?
	@./scripts/verify-grafana-mcp.sh

mcp-serve: ## Run mcp-grafana locally over streamable-http on :8000
	@set -a && . ./.env && set +a && \
	docker run --rm -p 8000:8000 \
		-e GRAFANA_URL="$$GRAFANA_URL" \
		-e GRAFANA_SERVICE_ACCOUNT_TOKEN="$$GRAFANA_SERVICE_ACCOUNT_TOKEN" \
		mcp/grafana -t streamable-http --address 0.0.0.0:8000

compliance: ## Run the hackathon AI-dependency guard
	@./scripts/check-ai-compliance.sh

sim: ## Run a healthy render farm for 10 minutes
	@cd telemetry-sim && uv run farm.py --duration 600

inject-incident: ## Healthy baseline, then the asset v7 failure at t+120s
	@cd telemetry-sim && uv run farm.py --duration 600 --inject-incident --incident-at 120

backfill: ## Fast-forward 30 minutes of history so dashboards look lived-in
	@cd telemetry-sim && uv run farm.py --duration 1800 --speed 10
