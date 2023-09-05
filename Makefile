PYTEST_ARGS=-v -rsx -x

.PHONY: test integration-test lint shell

ifeq ($(shell uname), Darwin)
SSH_SOCKET := /run/host-services/ssh-auth.sock
else
SSH_SOCKET := ${SSH_AUTH_SOCKET}
endif

.env: .env-example
	cp .env-example .env

test: .env
	SSH_AUTH_SOCK=$(SSH_SOCKET) docker compose run tests tox $(TOX_ARGS) -- -m "not integration" $(PYTEST_ARGS)

integration-test: .env
	SSH_AUTH_SOCK=$(SSH_SOCKET) docker compose run tests tox $(TOX_ARGS) -- -m "integration" $(PYTEST_ARGS)

lint: .env
	docker compose run lint /bin/lint $(ARGS)

shell: .env
	SSH_AUTH_SOCK=$(SSH_SOCKET) docker compose run tests /app/scripts/shell.sh
