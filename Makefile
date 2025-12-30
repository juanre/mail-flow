# Mailflow - Juan's email processing
.PHONY: help train train-dry metrics status test

help:
	@echo "Training:"
	@echo "  make train-dry DIR=~/Mail/folder    Dry-run (learn only)"
	@echo "  make train DIR=~/Mail/folder        Train + execute workflows"
	@echo "  make train-force DIR=~/Mail/folder  Reprocess all emails"
	@echo ""
	@echo "Monitoring:"
	@echo "  make metrics    Show classifier stats"
	@echo "  make status     Show all learning data"
	@echo "  make db-stats   Database table sizes"
	@echo ""
	@echo "Development:"
	@echo "  make test       Run tests"
	@echo "  make sync       uv sync"

# Training
train-dry:
ifndef DIR
	$(error Usage: make train-dry DIR=~/Mail/folder)
endif
	uv run mailflow fetch files "$(DIR)" --dry-run $(if $(MAX),--max-emails $(MAX),)

train:
ifndef DIR
	$(error Usage: make train DIR=~/Mail/folder)
endif
	uv run mailflow fetch files "$(DIR)" $(if $(MAX),--max-emails $(MAX),)

train-force:
ifndef DIR
	$(error Usage: make train-force DIR=~/Mail/folder)
endif
	uv run mailflow fetch files "$(DIR)" --force $(if $(MAX),--max-emails $(MAX),)

train-gmail:
	uv run mailflow fetch gmail --query "$(or $(QUERY),label:INBOX newer_than:1d)" $(if $(MAX),--max-results $(MAX),)

# Monitoring
metrics:
	uv run mailflow archivist-metrics

status:
	@echo "=== Database ==="
	@psql -d archivist_mailflow -t -c "SELECT 'Decisions: ' || COUNT(*) FROM archivist_mailflow.decisions;"
	@psql -d archivist_mailflow -t -c "SELECT 'Feedback: ' || COUNT(*) FROM archivist_mailflow.feedback;"
	@psql -d archivist_mailflow -t -c "SELECT 'Embeddings: ' || COUNT(*) FROM archivist_mailflow.embeddings;"
	@echo ""
	@echo "=== Local criteria ==="
	@cat ~/.local/share/mailflow/criteria_instances.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Training examples: {len(d)}')" || echo "No local data"

db-stats:
	@psql -d archivist_mailflow -c "\
		SELECT schemaname || '.' || relname AS table, \
			   pg_size_pretty(pg_total_relation_size(relid)) AS size, \
			   n_live_tup AS rows \
		FROM pg_stat_user_tables \
		WHERE schemaname = 'archivist_mailflow' \
		ORDER BY pg_total_relation_size(relid) DESC;"

# Development
test:
	uv run pytest -q

sync:
	uv sync

# Database
db-backup:
	@mkdir -p backups
	pg_dump archivist_mailflow > backups/archivist_mailflow_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Backup saved to backups/"

db-reset:
	@echo "WARNING: This deletes all learning data!"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	psql -d archivist_mailflow -c "TRUNCATE archivist_mailflow.feedback, archivist_mailflow.embeddings, archivist_mailflow.decisions CASCADE;"
	@echo "Done."
