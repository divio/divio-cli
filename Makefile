PYTEST_ARGS=-v -rsx -x

.PHONY: test integration-test lint shell


.env: .env-example
	cp .env-example .env

test: .env
	docker compose run tests tox $(TOX_ARGS) -- -m "not integration" $(PYTEST_ARGS)

integration-test: .env
	docker compose run tests tox $(TOX_ARGS) -- -m "integration" $(PYTEST_ARGS)

lint: .env
	docker compose run lint /bin/lint $(ARGS)

shell: .env
	docker compose run tests /app/scripts/shell.sh
