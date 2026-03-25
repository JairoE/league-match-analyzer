.PHONY: help install api-dev worker-dev worker-dev-verbose llm-dev db-up db-down db-migrate db-reset db-revision lint test test-logs backfill-extraction backfill-extraction-dry backfill-rank score-actions score-account-matches score-account-matches-dry account-match-stats aggregate-actions-debug compare-actions-debug llm-analysis-debug capture-riot-fixtures print-champion-ids

help:
	@echo "Available targets:"
	@echo "  install      Install all services in dev mode"
	@echo "  api-dev      Start API with hot reload"
	@echo "  worker-dev   Start ARQ background worker"
	@echo "  llm-dev      Start LLM worker"
	@echo "  db-up        Start Postgres + Redis via Docker"
	@echo "  db-down      Stop Docker services"
	@echo "  db-migrate   Apply Alembic migrations"
	@echo "  db-reset     Clear all data and run migrations"
	@echo "  db-revision  Create new Alembic migration"
	@echo "  lint         Run backend + frontend lint gates"
	@echo "  test         Run pytest on all services"
	@echo "  score-actions  Enqueue score_actions_job for a single match (MATCH_ID=...)"
	@echo "  score-account-matches  Enqueue score_actions_job for all unscored matches for an account (RIOT_ACCOUNT_ID=... or RIOT_ID=name#NA1)"
	@echo "  score-account-matches-dry  Print how many unscored matches would be scored for an account (RIOT_ACCOUNT_ID=... or RIOT_ID=name#NA1)"
	@echo "  account-match-stats  Show total vs scored matches for an account (RIOT_ACCOUNT_ID=... or RIOT_ID=name#NA1)"
	@echo "  aggregate-actions-debug  Print action aggregates for account (RIOT_ACCOUNT_ID= or RIOT_ID=...)"
	@echo "  compare-actions-debug  Print action comparison (gaps + bias) for account (RIOT_ACCOUNT_ID= or RIOT_ID=...)"
	@echo "  llm-analysis-debug  Run LLM analysis for account+champion (RIOT_ID=... CHAMPION=157 [RANK_TIER=GOLD] [DRY_RUN=1])"
	@echo "  capture-riot-fixtures  Capture live Riot JSON fixtures for tests"
	@echo "  print-champion-ids  Print Riot championId -> name mapping from Data Dragon"

install:
	python3 -m venv .venv || true
	./.venv/bin/python -m pip install --upgrade pip setuptools wheel
	./.venv/bin/python -m pip install -e services/api[dev]
	./.venv/bin/python -m pip install -e services/llm[dev]

api-dev:
	./.venv/bin/uvicorn --app-dir services/api main:app --reload --host 0.0.0.0 --port 8000

worker-dev:
	cd services/api && ../../.venv/bin/arq app.services.background_jobs.WorkerSettings

worker-dev-verbose:
	cd services/api && LOG_LEVEL=DEBUG ../../.venv/bin/arq app.services.background_jobs.WorkerSettings

llm-dev:
	cd services/llm && python main.py

db-up:
	cd infra/compose && docker compose up -d

db-down:
	cd infra/compose && docker compose down

db-migrate:
	cd services/api && ../../.venv/bin/alembic upgrade head

db-reset:
	cd infra/compose && docker compose down -v
	cd infra/compose && docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	cd services/api && ../../.venv/bin/alembic upgrade head

db-revision:
	@read -p "Migration message: " msg; \
	cd services/api && ../../.venv/bin/alembic revision --autogenerate -m "$$msg"

lint:
	./.venv/bin/ruff check services/api services/llm

test:
	./.venv/bin/pytest services/api services/llm

test-logs:
	./.venv/bin/pytest services/api services/llm -v -s

backfill-extraction:
	./.venv/bin/python scripts/backfill_extraction.py

backfill-extraction-dry:
	./.venv/bin/python scripts/backfill_extraction.py --dry-run

backfill-rank:
	./.venv/bin/python scripts/backfill_rank_on_vectors.py

score-actions:
	@if [ -z "$$MATCH_ID" ]; then \
		echo "Usage: make score-actions MATCH_ID=NA1_1234567890"; \
		exit 1; \
	fi
	./.venv/bin/python scripts/score_actions_for_match.py --match-id "$$MATCH_ID"

score-account-matches:
	@if [ -z "$$RIOT_ACCOUNT_ID" ] && [ -z "$$RIOT_ID" ]; then \
		echo "Usage: make score-account-matches RIOT_ACCOUNT_ID=<uuid> or RIOT_ID=name#NA1"; \
		exit 1; \
	fi; \
	if [ -z "$$RIOT_ACCOUNT_ID" ]; then \
		echo "Resolving riot account ID for $$RIOT_ID..."; \
		RIOT_ACCOUNT_ID=$$(docker exec league_postgres psql -U league -d league -t -c "\
		  SELECT id FROM riot_account \
		  WHERE riot_id = '$$RIOT_ID' \
		  LIMIT 1" | tr -d '[:space:]'); \
		if [ -z "$$RIOT_ACCOUNT_ID" ]; then \
			echo "No riot_account found for RIOT_ID=$$RIOT_ID"; \
			exit 1; \
		fi; \
		echo "Resolved RIOT_ACCOUNT_ID=$$RIOT_ACCOUNT_ID"; \
	else \
		RIOT_ACCOUNT_ID="$$RIOT_ACCOUNT_ID"; \
	fi; \
	docker exec league_postgres psql -U league -d league -t -c "\
	  SELECT m.game_id FROM match m \
	   JOIN riot_account_match ram ON ram.match_id = m.id \
	   WHERE ram.riot_account_id = '$$RIOT_ACCOUNT_ID' \
	     AND m.id NOT IN (SELECT DISTINCT match_id FROM match_action WHERE delta_w IS NOT NULL)" \
	  | xargs -I{} make score-actions MATCH_ID={}

score-account-matches-dry:
	@if [ -z "$$RIOT_ACCOUNT_ID" ] && [ -z "$$RIOT_ID" ]; then \
		echo "Usage: make score-account-matches-dry RIOT_ACCOUNT_ID=<uuid> or RIOT_ID=name#NA1"; \
		exit 1; \
	fi; \
	if [ -z "$$RIOT_ACCOUNT_ID" ]; then \
		echo "Resolving riot account ID for $$RIOT_ID..."; \
		RIOT_ACCOUNT_ID=$$(docker exec league_postgres psql -U league -d league -t -c "\
		  SELECT id FROM riot_account \
		  WHERE riot_id = '$$RIOT_ID' \
		  LIMIT 1" | tr -d '[:space:]'); \
		if [ -z "$$RIOT_ACCOUNT_ID" ]; then \
			echo "No riot_account found for RIOT_ID=$$RIOT_ID"; \
			exit 1; \
		fi; \
		echo "Resolved RIOT_ACCOUNT_ID=$$RIOT_ACCOUNT_ID"; \
	else \
		RIOT_ACCOUNT_ID="$$RIOT_ACCOUNT_ID"; \
	fi; \
	COUNT=$$(docker exec league_postgres psql -U league -d league -t -c "\
	  SELECT COUNT(*) FROM match m \
	   JOIN riot_account_match ram ON ram.match_id = m.id \
	   WHERE ram.riot_account_id = '$$RIOT_ACCOUNT_ID' \
	     AND m.id NOT IN (SELECT DISTINCT match_id FROM match_action WHERE delta_w IS NOT NULL)" | tr -d '[:space:]'); \
	echo "$$COUNT matches would be scored for RIOT_ACCOUNT_ID=$$RIOT_ACCOUNT_ID"

account-match-stats:
	@if [ -z "$$RIOT_ACCOUNT_ID" ] && [ -z "$$RIOT_ID" ]; then \
		echo "Usage: make account-match-stats RIOT_ACCOUNT_ID=<uuid> or RIOT_ID=name#NA1"; \
		exit 1; \
	fi; \
	if [ -z "$$RIOT_ACCOUNT_ID" ]; then \
		echo "Resolving riot account ID for $$RIOT_ID..."; \
		RIOT_ACCOUNT_ID=$$(docker exec league_postgres psql -U league -d league -t -c "\
		  SELECT id FROM riot_account \
		  WHERE riot_id = '$$RIOT_ID' \
		  LIMIT 1" | tr -d '[:space:]'); \
		if [ -z "$$RIOT_ACCOUNT_ID" ]; then \
			echo "No riot_account found for RIOT_ID=$$RIOT_ID"; \
			exit 1; \
		fi; \
		echo "Resolved RIOT_ACCOUNT_ID=$$RIOT_ACCOUNT_ID"; \
	else \
		RIOT_ACCOUNT_ID="$$RIOT_ACCOUNT_ID"; \
	fi; \
	TOTAL=$$(docker exec league_postgres psql -U league -d league -t -c "\
	  SELECT COUNT(DISTINCT m.id) FROM match m \
	   JOIN riot_account_match ram ON ram.match_id = m.id \
	   WHERE ram.riot_account_id = '$$RIOT_ACCOUNT_ID'" | tr -d '[:space:]'); \
	SCORED=$$(docker exec league_postgres psql -U league -d league -t -c "\
	  SELECT COUNT(DISTINCT m.id) FROM match m \
	   JOIN riot_account_match ram ON ram.match_id = m.id \
	   JOIN match_action ma ON ma.match_id = m.id \
	   WHERE ram.riot_account_id = '$$RIOT_ACCOUNT_ID' \
	     AND ma.delta_w IS NOT NULL" | tr -d '[:space:]'); \
	REMAINING=$$((TOTAL - SCORED)); \
	echo "Account $$RIOT_ACCOUNT_ID: total_matches=$$TOTAL scored_matches=$$SCORED remaining_to_score=$$REMAINING"

aggregate-actions-debug:
	@if [ -z "$$RIOT_ACCOUNT_ID" ] && [ -z "$$RIOT_ID" ]; then \
		echo "Usage: make aggregate-actions-debug RIOT_ACCOUNT_ID=<uuid> or RIOT_ID=name#NA1"; \
		exit 1; \
	fi
	./.venv/bin/python scripts/aggregate_actions_debug.py $$([ -n "$$RIOT_ACCOUNT_ID" ] && echo "--riot-account-id $$RIOT_ACCOUNT_ID" || echo "--riot-id $$RIOT_ID")

compare-actions-debug:
	@if [ -z "$$RIOT_ACCOUNT_ID" ] && [ -z "$$RIOT_ID" ]; then \
		echo "Usage: make compare-actions-debug RIOT_ACCOUNT_ID=<uuid> or RIOT_ID=name#NA1"; \
		exit 1; \
	fi
	./.venv/bin/python scripts/compare_actions_debug.py $$([ -n "$$RIOT_ACCOUNT_ID" ] && echo "--riot-account-id $$RIOT_ACCOUNT_ID" || echo "--riot-id $$RIOT_ID")

llm-analysis-debug:
	@if [ -z "$$RIOT_ACCOUNT_ID" ] && [ -z "$$RIOT_ID" ]; then \
		echo "Usage: make llm-analysis-debug RIOT_ID=name#NA1 CHAMPION=157 [RANK_TIER=GOLD] [DRY_RUN=1]"; \
		exit 1; \
	fi
	@if [ -z "$$CHAMPION" ]; then \
		echo "CHAMPION is required (e.g. CHAMPION=157)"; \
		exit 1; \
	fi
	./.venv/bin/python scripts/llm_analysis_debug.py $$([ -n "$$RIOT_ACCOUNT_ID" ] && echo "--riot-account-id $$RIOT_ACCOUNT_ID" || echo "--riot-id $$RIOT_ID") --champion $$CHAMPION $$([ -n "$$RANK_TIER" ] && echo "--rank-tier $$RANK_TIER") $$([ -n "$$DRY_RUN" ] && echo "--dry-run")

win-prob-model-training:
	./.venv/bin/python scripts/train_win_prob_model.py --input data/training.csv --output data/win_prob_model.joblib

capture-riot-fixtures:
	./.venv/bin/python scripts/capture_riot_test_fixtures.py --game-name damanjr --tag-line NA1 --count 40

print-champion-ids:
	./.venv/bin/python scripts/print_champion_ids.py
