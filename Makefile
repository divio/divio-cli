SHELL=/bin/bash

ENV_FILE=.env
PYTHON=python3
PYTHON_VENV=.venv
TOX_ARGS=-e py37
PYTEST_ARGS=-v -rsx

.PHONY: clean test test_integration lint


# helper
$(ENV_FILE):
	cp .env-example $(ENV_FILE)

$(PYTHON_VENV):
	rm -rf $(PYTHON_VENV) && \
	$(PYTHON) -m venv $(PYTHON_VENV) && \
	. $(PYTHON_VENV)/bin/activate && \
	pip install --upgrade pip tox && \
	pip install -e .

clean:
	rm -rf $(PYTHON_VENV)
	rm -rf test_data
	rm -rf .tox

# tests
test: | $(ENV_FILE) $(PYTHON_VENV)
	. $(PYTHON_VENV)/bin/activate && \
	. $(ENV_FILE) && \
	tox $(TOX_ARGS) -- -m "not integration" $(PYTEST_ARGS)

test_integration: | $(ENV_FILE) $(PYTHON_VENV)
	. $(PYTHON_VENV)/bin/activate && \
	. $(ENV_FILE) && \
	tox $(TOX_ARGS) -- -m "integration" $(PYTEST_ARGS)

# lint
lint:
	docker run --rm -e LINT_FOLDER_PYTHON=divio_cli -v $(CURDIR):/app divio/lint /bin/lint ${ARGS}
