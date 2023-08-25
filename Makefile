ZONE=dev.aldryn.net
TESTS=divio_cli/test/
TEST_PROJECT_NAME=cli-tests-app
TEST_PROJECT_ID=96597
TEST_PROJECT_UUID=lmzdb62475dtvdkplxnd3k2fdu
TEST_PROJECT_DEPLOYMENT_UUID=r4bnltssuvfn7g7kz7hw4yytmi

PYTHON=python3.11
PYTHON_VENV=env

.PHONY: clean login lint


clean:
	rm -rf $(PYTHON_VENV)

lint:
	docker run --rm -e LINT_FOLDER_PYTHON=divio_cli -v $(CURDIR):/app divio/lint /bin/lint ${ARGS}

$(PYTHON_VENV): requirements.txt
	rm -rf $(PYTHON_VENV) && \
	$(PYTHON) -m venv $(PYTHON_VENV) && \
	. $(PYTHON_VENV)/bin/activate && \
	pip install pip --upgrade && \
	pip install -r ./requirements.txt && \
	pip install -e . && \
	pip install tox

integration-test: | $(PYTHON_VENV)
	. $(PYTHON_VENV)/bin/activate && \
	TEST_KEEP_PROJECT=1 \
	TEST_ZONE="$(ZONE)" \
	TEST_PROJECT_NAME="$(TEST_PROJECT_NAME)" \
	TEST_PROJECT_ID=$(TEST_PROJECT_ID) \
	TEST_PROJECT_UUID=$(TEST_PROJECT_UUID) \
	TEST_PROJECT_DEPLOYMENT_UUID=$(TEST_PROJECT_DEPLOYMENT_UUID) \
		tox -e py3.11 -- $(TESTS) -m "integration" -v -rs -s -x

setup: $(PYTHON_VENV)
	. $(PYTHON_VENV)/bin/activate && \
	divio -z $(ZONE) app setup $(TEST_PROJECT_NAME)

divio: $(PYTHON_VENV)
	. $(PYTHON_VENV)/bin/activate && \
	TEST_ZONE="$(ZONE)" \
	TEST_PROJECT_NAME="$(TEST_PROJECT_NAME)" \
	TEST_PROJECT_ID=$(TEST_PROJECT_ID) \
	TEST_PROJECT_UUID=$(TEST_PROJECT_UUID) \
	TEST_PROJECT_DEPLOYMENT_UUID=$(TEST_PROJECT_DEPLOYMENT_UUID) \
		divio $(args)
