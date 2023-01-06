lint:
	docker run --rm -eLINT_FOLDER_PYTHON=divio_cli -v $(CURDIR):/app divio/lint /bin/lint ${ARGS}
