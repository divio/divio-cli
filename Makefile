lint:
	docker run --rm -e LINT_FOLDER_PYTHON=divio_cli -v $(CURDIR):/app divio/lint /bin/lint ${ARGS}
